/-!
# ProofForge FriCAS Translator
## `lean_to_fricas : Expr → MetaM String`

Serializes a Lean 4 `Expr` representing a real-valued scalar expression to a
FriCAS-compatible integrand string.

### Operator coverage

| Lean 4 expression       | FriCAS output          |
|-------------------------|------------------------|
| `a + b`                 | `a + b`                |
| `a - b`                 | `a - b`                |
| `a * b`                 | `a * b`                |
| `a / b`                 | `a / b`                |
| `a ^ n`                 | `a ^ n`                |
| `-a`                    | `-a`                   |
| numeric literal         | `"n"`                  |
| free variable `x`       | `"x"`                  |
| `Real.log x`            | `log(x)`               |
| `Real.exp x`            | `exp(x)`               |
| `Real.arctan x`         | `atan(x)`              |
| `Real.sin x`            | `sin(x)`               |
| `Real.cos x`            | `cos(x)`               |
| `Real.sqrt x`           | `sqrt(x)`              |

### Round-trip contract

Given a `HasDerivAt f f' x` theorem from `RischVerification.lean`, calling
`lean_to_fricas` on `f'` (extracted via `integrand_of_has_deriv_at`) produces
a string that, when passed to `FriCAS.integrate(·, x)`, yields back `f`.

### Precedence model

Parentheses are inserted when an inner expression has strictly lower precedence
than the outer context.  FriCAS and standard mathematical precedence agree:
`^` (75) > `*/` (70) > `+-` (65).  The Lean precedences used here are
deliberately matched to FriCAS so that no spurious parentheses appear.
-/
import Mathlib.Tactic

namespace ProofForge.FriCAS

open Lean Meta

-- ---------------------------------------------------------------------------
-- Internal precedence constants
-- ---------------------------------------------------------------------------

private def precAdd : Nat := 65
private def precMul : Nat := 70
private def precPow : Nat := 75
private def precAtom : Nat := 100

private def parenIf (cond : Bool) (s : String) : String :=
  if cond then s!"({s})" else s

-- ---------------------------------------------------------------------------
-- Main function
-- ---------------------------------------------------------------------------

/--
Serialize a Lean 4 `Expr` to a FriCAS-compatible expression string.

Unrecognized subexpressions are rendered as `"??"` followed by the
constant name so the caller can detect incomplete translations without
silently producing wrong results.
-/
def lean_to_fricas (e : Expr) : MetaM String :=
  go 0 e
where
  go (outerPrec : Nat) : Expr → MetaM String
    | e => do
      let e ← whnfR e
      -- Fast path for numerals (handles OfNat.ofNat and .lit)
      if let some n := e.numeral? then return toString n
      match e with
      -- Free variables (integration variable x, hypotheses)
      | .fvar fid => do
          let lctx ← getLCtx
          return match lctx.find? fid with
            | some decl => decl.userName.toString
            | none      => "?fvar"
      | .app .. =>
          let fn   := e.getAppFn
          let args := e.getAppArgs
          match fn with
          -- ── Arithmetic operators ────────────────────────────────────────
          | .const `HAdd.hAdd _ =>
              if args.size < 6 then return "??HAdd"
              let ls ← go precAdd           args[4]!
              let rs ← go (precAdd + 1)    args[5]!
              return parenIf (outerPrec > precAdd) s!"{ls} + {rs}"
          | .const `HSub.hSub _ =>
              if args.size < 6 then return "??HSub"
              let ls ← go precAdd           args[4]!
              let rs ← go (precAdd + 1)    args[5]!
              return parenIf (outerPrec > precAdd) s!"{ls} - {rs}"
          | .const `HMul.hMul _ =>
              if args.size < 6 then return "??HMul"
              let ls ← go precMul           args[4]!
              let rs ← go (precMul + 1)    args[5]!
              return parenIf (outerPrec > precMul) s!"{ls} * {rs}"
          | .const `HDiv.hDiv _ =>
              if args.size < 6 then return "??HDiv"
              let ls ← go precMul           args[4]!
              let rs ← go (precMul + 1)    args[5]!
              return parenIf (outerPrec > precMul) s!"{ls} / {rs}"
          | .const `HPow.hPow _ =>
              if args.size < 6 then return "??HPow"
              let ls ← go precPow           args[4]!
              let rs ← go 0                args[5]!
              return parenIf (outerPrec > precPow) s!"{ls} ^ {rs}"
          | .const `Neg.neg _ =>
              if args.size < 3 then return "??Neg"
              let inner ← go precAtom args[2]!
              return parenIf (outerPrec > precAtom) s!"-{inner}"
          -- ── Standard Mathlib special functions ──────────────────────────
          | .const `Real.log _ =>
              if args.size < 1 then return "??Real.log"
              let arg ← go 0 args[0]!
              return s!"log({arg})"
          | .const `Real.exp _ =>
              if args.size < 1 then return "??Real.exp"
              let arg ← go 0 args[0]!
              return s!"exp({arg})"
          | .const `Real.arctan _ =>
              if args.size < 1 then return "??Real.arctan"
              let arg ← go 0 args[0]!
              return s!"atan({arg})"
          | .const `Real.sin _ =>
              if args.size < 1 then return "??Real.sin"
              let arg ← go 0 args[0]!
              return s!"sin({arg})"
          | .const `Real.cos _ =>
              if args.size < 1 then return "??Real.cos"
              let arg ← go 0 args[0]!
              return s!"cos({arg})"
          | .const `Real.sqrt _ =>
              if args.size < 1 then return "??Real.sqrt"
              let arg ← go 0 args[0]!
              return s!"sqrt({arg})"
          -- ── Fallback ───────────────────────────────────────────────────
          | _ =>
              if let some n := e.numeral? then return toString n
              return s!"??{fn.constName?.getD `unknown}"
      | _ => return s!"??expr"

-- ---------------------------------------------------------------------------
-- Integrand extraction
-- ---------------------------------------------------------------------------

/--
Given a term of type `HasDerivAt f f' x`, return `lean_to_fricas f'`.

The `HasDerivAt` constructor `HasDerivAt.mk` has type:
  `HasDerivAt f f' x : Prop`
where `f' : ℝ` is the derivative.  As an `Expr`, the outermost application
is `HasDerivAt f f' x` — a 3-argument application after the implicit type
argument.  We extract the second explicit argument `f'`.

Expected structure (4 explicit args + implicit type):
  `.app (.app (.app (.app hasDerivAt typeArg) f) f') x`
-/
def integrand_of_has_deriv_at (goal : Expr) : MetaM String := do
  -- Strip implicit arguments by checking the constructor
  match goal.getAppFnArgs with
  | (`HasDerivAt, #[_, _f, f', _x]) => lean_to_fricas f'
  | _ => throwError "goal is not of the form HasDerivAt f f' x"

end ProofForge.FriCAS
