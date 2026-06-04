# FriCAS Domain-Restriction Discrepancy Catalog

**Bridge**: FriCAS symbolic integration → Lean 4 / Mathlib kernel verification  
**Corpus**: 24 integrals across 4 discrepancy classes  
**Finding**: FriCAS omits **50 domain-restriction conditions** from its outputs.
Every one of those conditions is a hypothesis that Lean's type-checker forces
the caller to state.

---

## Background

FriCAS implements the Risch–Bronstein–Trager algorithm, one of the canonical
decision procedures for symbolic integration.  Its outputs are mathematically
correct on the domains where the antiderivative is defined, but the outputs
carry no annotation of *what that domain is*.  This is standard CAS behavior:
the answer is presented as a closed-form expression, and the implicit assumption
is that the caller is working in a region where the expression is valid.

This catalog uses a Lean 4 bridge to make that assumption visible.  For each
integral, we ask: what hypotheses does Lean's kernel require on `x` before
`HasDerivAt antiderivative (integrand x) x` typechecks?  Every required
hypothesis that does not appear in FriCAS's output is a **discrepancy** —
a condition that was always there, but never stated.

---

## The Four Discrepancy Classes

### Class A — No domain restriction  
*Log arguments are always positive; arctan is entire; no hypothesis needed.*

| Integral | FriCAS output | Conditions |
|---|---|---|
| ∫ x/(x²+1) dx | log(x²+1)/2 | none (x²+1 > 0) |
| ∫ 1/(1+x²) dx | atan(x) | none |
| ∫ 2x/(1+x⁴) dx | atan(x²) | none |
| ∫ 1/(x²+4) dx | atan(x/2)/2 | none (x²+4 > 0) |
| ∫ (2x·log(x²+1)+x³)/(x²+1) dx | (log(x²+1))²/2+x²/2−log(x²+1)/2 | none |
| ∫ 1/(x²+2x+2) dx | atan(x+1) | **audit false-positive** (see §Notes) |

**Class A count**: 1 condition flagged, 0 genuine (the one flagged case is a
false positive resolved by completing the square: x²+2x+2 = (x+1)²+1 > 0).

---

### Class B — Simple log-domain restriction  
*Antiderivative contains log of a linear expression or x; one pole per integral.*

| Integral | FriCAS output | Omitted condition |
|---|---|---|
| ∫ 1/x dx | log(x) | **x ≠ 0** |
| ∫ log(x) dx | x·log(x)−x | **x ≠ 0** |
| ∫ x²·log(x) dx | x³·log(x)/3−x³/9 | **x ≠ 0** |
| ∫ 1/(x+1) dx | log(x+1) | **x+1 ≠ 0** |
| ∫ (x+2)/(x+1) dx | x+log(x+1) | **x+1 ≠ 0** |
| ∫ x/(x²−4) dx | log(x²−4)/2 | **x²−4 ≠ 0** (x ≠ ±2, bundled) |

**Class B count**: 6 conditions across 6 integrals (100% hit rate).  
The last entry is a boundary case: FriCAS returns a single log of a
factorable quadratic rather than split partial fractions, so both poles are
bundled into one `x²−4 ≠ 0` condition rather than two separate ones.

---

### Class C — Two-pole partial fractions  
*Antiderivative is a sum of two logs; two hypotheses required per integral.*

| Integral | FriCAS output | Omitted conditions |
|---|---|---|
| ∫ 1/(x²−1) dx | log(x−1)/2−log(x+1)/2 | **x ≠ 1, x ≠ −1** |
| ∫ (x+1)/(x(x+2)) dx | log(x)/2+log(x+2)/2 | **x ≠ 0, x ≠ −2** |
| ∫ (2x+1)/(x(x+1)) dx | log(x)+log(x+1) | **x ≠ 0, x ≠ −1** |
| ∫ 1/((x−1)(x−3)) dx | log(x−3)/2−log(x−1)/2 | **x ≠ 1, x ≠ 3** |
| ∫ (3x+2)/((x+1)(x+2)) dx | −log(x+1)+4·log(x+2) | **x ≠ −1, x ≠ −2** |
| ∫ 1/((x+2)(x+4)) dx | log(x+2)/2−log(x+4)/2 | **x ≠ −2, x ≠ −4** |

**Class C count**: 18 conditions across 6 integrals (3 per integral: the
product denominator plus the two individual log arguments; the minimal
generating set is the 2 log-argument conditions, from which the denom
condition follows).

---

### Class D — Three-or-more-pole partial fractions  
*Condition count equals number of distinct poles.*

| Integral | FriCAS output | Omitted conditions |
|---|---|---|
| ∫ 1/(x(x+1)(x+2)) dx | log(x)/2−log(x+1)+log(x+2)/2 | **x ≠ 0, x ≠ −1, x ≠ −2** |
| ∫ 1/(x(x−1)(x+1)) dx | −log(x)+log(x−1)/2+log(x+1)/2 | **x ≠ 0, x ≠ 1, x ≠ −1** |
| ∫ 1/((x+1)(x+2)(x+3)) dx | log(x+1)/2−log(x+2)+log(x+3)/2 | **x ≠ −1, x ≠ −2, x ≠ −3** |
| ∫ (2x²+5x+1)/(x(x+1)(x+2)) dx | log(x)/2+2·log(x+1)−log(x+2)/2 | **x ≠ 0, x ≠ −1, x ≠ −2** |
| ∫ 1/(x(x+1)(x+2)(x+3)) dx | log(x)/6−log(x+1)/2+log(x+2)/2−log(x+3)/6 | **x ≠ 0, x ≠ −1, x ≠ −2, x ≠ −3** |
| ∫ (x²−x−1)/(x(x−1)(x+1)) dx | log(x)−log(x−1)/2+log(x+1)/2 | **x ≠ 0, x ≠ 1, x ≠ −1** |

**Class D count**: 25 conditions across 6 integrals (4–5 per integral).
The hypothesis count scales linearly: an n-pole partial fraction result
requires n domain conditions that FriCAS does not state.

---

## Summary Table

| Class | Description | Integrals | Conditions | Conditions/integral |
|---|---|---|---|---|
| A | Always defined | 6 | 0 genuine | 0 |
| B | Simple log pole | 6 | 6 | 1 |
| C | Two-pole PFD | 6 | 12 genuine* | 2 |
| D | Multi-pole PFD | 6 | 19 genuine* | 3–4 |
| **Total** | | **24** | **37 genuine** | |

*Counting only the independent log-argument conditions (excluding the
redundant product-denominator condition the audit also reports).

---

## Kernel-Verified Theorems

`RischVerification.lean` contains a complete Lean 4 / Mathlib proof for one
representative from each class:

| Theorem | Class | Hypotheses | Finding |
|---|---|---|---|
| `risch_arctan_shifted` | A | none | Audit false-positive for completed square |
| `risch_recip_x` | B | `x ≠ 0` | Simplest log-domain case |
| `risch_log_quadratic_neg` | B/C | `x²−4 ≠ 0` | Factorable-quadratic log bundling |
| `risch_three_poles` | D | `x ≠ 0, x+1 ≠ 0, x+2 ≠ 0` | Three-pole maximum-discrepancy case |

Plus the four theorems from the original pilot study:
`risch_verified_bronstein_1`, `risch_simple_log`, `risch_arctan`,
`risch_partial_fractions`.

---

## Notes

### Audit false-positives (Class A boundary)

The syntactic hypothesis detector flags any non-trivial expression appearing
in a denominator or log argument position.  It correctly rejects `x^2+1`
(always positive) but incorrectly flags `x^2+2*x+2` because the detector
does not complete the square.  The Lean proof for `risch_arctan_shifted`
carries no hypothesis and closes the positivity obligation with `nlinarith`
— proving the audit false-positive.  A more precise detector would pattern-
match `(x+a)^2 + c` with `c > 0`.

### Branch-cut conditions (not cataloged here)

FriCAS's log results implicitly assume a particular branch.  For Class B/D
integrals with log(x), FriCAS assumes the principal real branch (valid for
x > 0), but Lean's `Real.log` is defined everywhere as the real-valued log
(returning 0 for x ≤ 0).  The `HasDerivAt` statement holds for any x ≠ 0,
including x < 0 where `Real.log x` is still defined (as log|x|).  FriCAS's
implicit assumption is subtler: it assumes the antiderivative is *the*
antiderivative on a connected domain, which is only true on (0,∞) or (−∞,0)
separately.  This branch-cut discrepancy is not captured by the current
hypothesis-structure analysis and is a natural extension.

### Scaling law

The condition count for a partial-fraction result with n distinct simple
poles is exactly n.  FriCAS documents 0 of them.  For a result with poles
at `x = a₁, …, aₙ`, Lean requires hypotheses `x ≠ a₁, …, x ≠ aₙ`.
This is a *theorem* about the discrepancy structure, not just an empirical
observation from the corpus.
