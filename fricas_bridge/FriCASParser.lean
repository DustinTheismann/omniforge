/-!
# ProofForge FriCAS → Lean 4 Expression Parser
## `fricas_to_lean_expr : String → TermElabM Expr`

Parses a FriCAS-format expression string and returns the corresponding
Lean 4 `Expr` in `ℝ`.

This is the inverse of `FriCASTranslator.lean`'s `lean_to_fricas`:

```
lean_to_fricas      :  Expr  →  MetaM String   (Lean → FriCAS)
fricas_to_lean_expr :  String → TermElabM Expr  (FriCAS → Lean)
```

### Strategy

Two-phase approach:
  1. **String conversion** (`fricas_text_to_lean_text`) — pure, no elaboration.
     Rewrites FriCAS syntax to syntactically valid Lean 4 term text.
  2. **Elaboration** (`fricas_to_lean_expr`) — parses the Lean 4 text using
     Lean's own `Lean.Parser.runParserCategory` and elaborates it with
     `Lean.Elab.Term.elabTerm` in the caller's local context.

Using Lean's own elaborator (rather than a hand-written `Expr` builder)
means that numeric coercions, typeclass resolution, and implicit arguments
are all handled automatically and remain correct as Mathlib evolves.

### Operator mapping

| FriCAS             | Lean 4                |
|--------------------|-----------------------|
| `log(arg)`         | `Real.log (arg)`      |
| `atan(arg)`        | `Real.arctan (arg)`   |
| `exp(arg)`         | `Real.exp (arg)`      |
| `sin(arg)`         | `Real.sin (arg)`      |
| `cos(arg)`         | `Real.cos (arg)`      |
| `sqrt(arg)`        | `Real.sqrt (arg)`     |
| `a^b`              | `a ^ b`               |
| `a/b`              | `a / b`               |
| `a*b`              | `a * b`               |
| `a+b`              | `a + b`               |
| `a-b`              | `a - b`               |

### Variable convention

FriCAS integration variable `x` maps to the Lean lambda binder.  Callers
are responsible for providing a `LocalContext` that includes the variable
they intend `x` to resolve to (typically a free variable `t : ℝ` for
antiderivative expressions, matching `RischVerification.lean` convention).

### Known limitation

`fricas_text_to_lean_text` uses simple string replacement and always wraps
function arguments in parentheses (e.g. `Real.log (x)` rather than the
normalised `Real.log x`).  The resulting `Expr` is semantically identical;
only the pretty-printed form differs from the convention in the claim files.
The Python companion `fricas_to_lean.py` produces normalised output for
testing purposes.
-/
import Mathlib.Tactic

namespace ProofForge.FriCAS

open Lean Elab Meta Term

-- ---------------------------------------------------------------------------
-- Phase 1 — pure string conversion
-- ---------------------------------------------------------------------------

private def addSpaces (s : String) : String :=
  s.replace "^" " ^ "
   |>.replace "/" " / "
   |>.replace "*" " * "
   |>.replace "+" " + "
   -- binary minus only; avoid double-spacing with existing spaces
   |>.replace "- " " - "
   |>.replace " -" " - "

/--
Convert a FriCAS expression string to a syntactically valid Lean 4 term string.

Special functions are rewritten: `log(` → `Real.log (`, etc.
Arithmetic operators are given surrounding spaces.

The result is suitable as input to `Lean.Parser.runParserCategory env \`term`.

**Note**: This function always wraps function arguments in parentheses, so it
produces `Real.log (x)` rather than the normalised `Real.log x`.  Both are
valid Lean 4; the extra parentheses are transparent to the elaborator.
-/
def fricas_text_to_lean_text (fricas : String) : String :=
  let s := fricas
  let s := s.replace "log("  "Real.log ("
  let s := s.replace "atan(" "Real.arctan ("
  let s := s.replace "exp("  "Real.exp ("
  let s := s.replace "sin("  "Real.sin ("
  let s := s.replace "cos("  "Real.cos ("
  let s := s.replace "sqrt(" "Real.sqrt ("
  -- Spacing around operators (applied after function rewrites to avoid
  -- touching the newly inserted spaces in "Real.log (")
  let s := addSpaces s
  -- Collapse multiple spaces to one
  s.split (· == ' ') |>.filter (· ≠ "") |> String.intercalate " "

-- ---------------------------------------------------------------------------
-- Phase 2 — elaboration
-- ---------------------------------------------------------------------------

/--
Parse a FriCAS expression string and elaborate it as a real-valued Lean 4 `Expr`.

Converts `fricas` to Lean 4 source text via `fricas_text_to_lean_text`, then
parses and elaborates it using Lean's own machinery.

The `expectedType` is `ℝ` by default.  The function is in `TermElabM` so it
has access to the caller's local context (including any free variable for `x`).
-/
def fricas_to_lean_expr (fricas : String) : TermElabM Expr := do
  let lean_text := fricas_text_to_lean_text fricas
  let env ← getEnv
  match Lean.Parser.runParserCategory env `term lean_text "<fricas_input>" with
  | .ok stx  => elabTerm stx (some (.const `Real []))
  | .error e => throwError s!"FriCAS parser: cannot parse '{fricas}' as Lean term: {e}"

/--
Parse a FriCAS antiderivative string and wrap it in a `fun (t : ℝ) => ⬝` lambda.

The resulting `Expr` has type `ℝ → ℝ` and can be supplied as the `f` argument
in `HasDerivAt f f' x` goals.
-/
def fricas_to_lean_lambda (fricas : String) : TermElabM Expr := do
  let body_text := fricas_text_to_lean_text fricas
  let lambda_text := s!"fun (t : ℝ) => {body_text}"
  let env ← getEnv
  match Lean.Parser.runParserCategory env `term lambda_text "<fricas_lambda>" with
  | .ok stx  => elabTerm stx none
  | .error e => throwError s!"FriCAS parser: cannot build lambda for '{fricas}': {e}"

end ProofForge.FriCAS
