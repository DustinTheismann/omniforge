-- Tier 1.5 — CAS Disagreement Kernel Adjudication.
--
-- CONTEXT: The three-CAS disagree_detector (Python, Tier 5.4) discovered that
-- FriCAS/Maxima and SymPy return syntactically different antiderivatives for
-- two Bronstein integrands:
--
--   bronstein_005  ∫ (x+1)/(x·(x+2)) dx
--     FriCAS/Maxima: log(x)/2 + log(x+2)/2          [factored PFD]
--     SymPy:         log(x²+2x)/2                    [product log]
--
--   bronstein_009  ∫ 1/(x·(x+1)·(x+2)) dx
--     FriCAS/Maxima: log(x)/2 − log(x+1) + log(x+2)/2
--     SymPy:         −log(x+1) + log(x²+2x)/2
--
-- FINDING: Both forms are PROVABLY EQUAL inside Lean's kernel under exactly
-- the hypotheses HasDerivAt requires (x ≠ 0, x+2 ≠ 0).  The apparent
-- three-CAS disagreement is resolved in a single step by Real.log_mul.
-- This file constitutes the kernel adjudication: the disagreement is
-- notational, not mathematical.
--
-- ADJUDICATION STRUCTURE (per integrand):
--   1. form_disagree_XXX_equivalent   — both antiderivatives are equal (ring + log_mul)
--   2. autodischarge_XXX_fricas_form  — FriCAS form HasDerivAt (from RischAutoDischarge)
--   3. autodischarge_XXX_sympy_form   — SymPy form HasDerivAt (derived independently)
--   4. adjudicate_XXX                 — both forms certify the same derivative
--
-- This is the first formally kernel-verified CAS agreement adjudication.
import Mathlib.Analysis.SpecialFunctions.Log.Deriv
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Deriv
import Mathlib.Tactic

noncomputable section
open Real

-- ============================================================
-- ADJUDICATION: bronstein_005  ∫ (x+1)/(x·(x+2)) dx
-- ============================================================

/-- The FriCAS/Maxima factored form and the SymPy product form are equal
    under the same hypotheses that any HasDerivAt proof requires. -/
theorem form_disagree_005_equivalent (x : ℝ) (hx : x ≠ 0) (hx2 : x + 2 ≠ 0) :
    Real.log x / 2 + Real.log (x + 2) / 2 = Real.log (x ^ 2 + 2 * x) / 2 := by
  have hfact : x ^ 2 + 2 * x = x * (x + 2) := by ring
  rw [hfact, Real.log_mul hx hx2]
  ring

/-- SymPy's product-form antiderivative for bronstein_005, proved independently
    (without importing RischAutoDischarge). -/
theorem autodischarge_005_sympy_form (x : ℝ) (hx : x ≠ 0) (hx2 : x + 2 ≠ 0) :
    HasDerivAt (fun t : ℝ => Real.log (t ^ 2 + 2 * t) / 2)
               ((x + 1) / (x * (x + 2))) x := by
  have harg : x ^ 2 + 2 * x ≠ 0 := by
    rw [show x ^ 2 + 2 * x = x * (x + 2) from by ring]
    exact mul_ne_zero hx hx2
  -- Derivative of t² + 2t is 2t + 2
  have hpoly : HasDerivAt (fun t : ℝ => t ^ 2 + 2 * t) (2 * x + 2) x := by
    have h1 : HasDerivAt (fun t : ℝ => t ^ 2) (2 * x) x := by
      have h := hasDerivAt_pow 2 x
      simpa [pow_one] using h
    have h2 : HasDerivAt (fun t : ℝ => 2 * t) 2 x := by
      have h := (hasDerivAt_id x).const_mul (2 : ℝ)
      simp only [id, mul_one] at h
      exact h
    have h3 := h1.add h2
    convert h3 using 1; ring
  -- Apply the log chain rule, then divide by 2
  have hchain := (hpoly.log harg).div_const 2
  convert hchain using 1
  field_simp [harg, mul_ne_zero hx hx2]
  rw [show x ^ 2 + 2 * x = x * (x + 2) from by ring]
  ring

/-- Kernel adjudication for bronstein_005: both antiderivative forms are
    accepted by the Lean kernel and compute the same derivative. -/
theorem adjudicate_005 (x : ℝ) (hx : x ≠ 0) (hx2 : x + 2 ≠ 0) :
    -- FriCAS/Maxima form
    HasDerivAt (fun t : ℝ => Real.log t / 2 + Real.log (t + 2) / 2)
               ((x + 1) / (x * (x + 2))) x ∧
    -- SymPy form
    HasDerivAt (fun t : ℝ => Real.log (t ^ 2 + 2 * t) / 2)
               ((x + 1) / (x * (x + 2))) x ∧
    -- They are the same function under the required domain conditions
    (∀ t : ℝ, t ≠ 0 → t + 2 ≠ 0 →
      Real.log t / 2 + Real.log (t + 2) / 2 = Real.log (t ^ 2 + 2 * t) / 2) := by
  refine ⟨?_, ?_, ?_⟩
  · -- FriCAS/Maxima form (identical to autodischarge_005 in RischAutoDischarge)
    have hL1 : HasDerivAt (fun t : ℝ => Real.log t / 2) (1 / (2 * x)) x := by
      have h := ((hasDerivAt_id x).log hx).div_const 2
      convert h using 1; field_simp [hx]
    have hg2 : HasDerivAt (fun t : ℝ => t + 2) 1 x := by
      have h := (hasDerivAt_id x).add (hasDerivAt_const x (2 : ℝ))
      simpa using h
    have hL2 : HasDerivAt (fun t : ℝ => Real.log (t + 2) / 2) (1 / (2 * (x + 2))) x := by
      have h := (hg2.log hx2).div_const 2
      convert h using 1; field_simp [hx2]
    have hF := hL1.add hL2
    convert hF using 1
    field_simp [hx, hx2, mul_ne_zero hx hx2]; ring
  · exact autodischarge_005_sympy_form x hx hx2
  · intro t ht ht2; exact form_disagree_005_equivalent t ht ht2

-- ============================================================
-- ADJUDICATION: bronstein_009  ∫ 1/(x·(x+1)·(x+2)) dx
-- ============================================================

/-- The FriCAS/Maxima factored form and SymPy's product form are equal. -/
theorem form_disagree_009_equivalent (x : ℝ) (hx : x ≠ 0) (hx3 : x + 2 ≠ 0) :
    Real.log x / 2 - Real.log (x + 1) + Real.log (x + 2) / 2 =
    -Real.log (x + 1) + Real.log (x ^ 2 + 2 * x) / 2 := by
  have hfact : x ^ 2 + 2 * x = x * (x + 2) := by ring
  rw [hfact, Real.log_mul hx hx3]
  ring

/-- SymPy's form for bronstein_009, proved independently. -/
theorem autodischarge_009_sympy_form (x : ℝ) (hx : x ≠ 0) (hx2 : x + 1 ≠ 0)
    (hx3 : x + 2 ≠ 0) :
    HasDerivAt (fun t : ℝ => -Real.log (t + 1) + Real.log (t ^ 2 + 2 * t) / 2)
               (1 / (x * (x + 1) * (x + 2))) x := by
  have harg : x ^ 2 + 2 * x ≠ 0 := by
    rw [show x ^ 2 + 2 * x = x * (x + 2) from by ring]
    exact mul_ne_zero hx hx3
  -- HasDerivAt of -log(t+1)
  have hg1 : HasDerivAt (fun t : ℝ => t + 1) 1 x := by
    simpa using (hasDerivAt_id x).add (hasDerivAt_const x (1 : ℝ))
  have hlog1 : HasDerivAt (fun t : ℝ => Real.log (t + 1)) (1 / (x + 1)) x := by
    have h := hg1.log hx2
    convert h using 1; field_simp [hx2]
  have hneg : HasDerivAt (fun t : ℝ => -Real.log (t + 1)) (-(1 / (x + 1))) x :=
    hlog1.neg
  -- HasDerivAt of log(t²+2t)/2
  have hpoly : HasDerivAt (fun t : ℝ => t ^ 2 + 2 * t) (2 * x + 2) x := by
    have h1 : HasDerivAt (fun t : ℝ => t ^ 2) (2 * x) x := by
      have h := hasDerivAt_pow 2 x; simpa [pow_one] using h
    have h2 : HasDerivAt (fun t : ℝ => 2 * t) 2 x := by
      have h := (hasDerivAt_id x).const_mul (2 : ℝ)
      simp only [id, mul_one] at h; exact h
    have h3 := h1.add h2
    convert h3 using 1; ring
  have hlog2 := (hpoly.log harg).div_const 2
  -- Combine
  have hF := hneg.add hlog2
  convert hF using 1
  have h123 : x * (x + 1) * (x + 2) ≠ 0 := mul_ne_zero (mul_ne_zero hx hx2) hx3
  field_simp [harg, h123]
  rw [show x ^ 2 + 2 * x = x * (x + 2) from by ring]
  ring

/-- Kernel adjudication for bronstein_009. -/
theorem adjudicate_009 (x : ℝ) (hx : x ≠ 0) (hx2 : x + 1 ≠ 0) (hx3 : x + 2 ≠ 0) :
    HasDerivAt (fun t : ℝ => Real.log t / 2 - Real.log (t + 1) + Real.log (t + 2) / 2)
               (1 / (x * (x + 1) * (x + 2))) x ∧
    HasDerivAt (fun t : ℝ => -Real.log (t + 1) + Real.log (t ^ 2 + 2 * t) / 2)
               (1 / (x * (x + 1) * (x + 2))) x ∧
    (∀ t : ℝ, t ≠ 0 → t + 2 ≠ 0 →
      Real.log t / 2 - Real.log (t + 1) + Real.log (t + 2) / 2 =
      -Real.log (t + 1) + Real.log (t ^ 2 + 2 * t) / 2) := by
  refine ⟨?_, ?_, ?_⟩
  · -- FriCAS/Maxima form (same as autodischarge_009)
    have hL1 : HasDerivAt (fun t : ℝ => Real.log t / 2) (1 / (2 * x)) x := by
      have h := ((hasDerivAt_id x).log hx).div_const 2
      convert h using 1; field_simp [hx]
    have hg1 : HasDerivAt (fun t : ℝ => t + 1) 1 x := by
      simpa using (hasDerivAt_id x).add (hasDerivAt_const x (1 : ℝ))
    have hL2 : HasDerivAt (fun t : ℝ => Real.log (t + 1)) (1 / (x + 1)) x := by
      have h := hg1.log hx2
      convert h using 1; field_simp [hx2]
    have hg2 : HasDerivAt (fun t : ℝ => t + 2) 1 x := by
      simpa using (hasDerivAt_id x).add (hasDerivAt_const x (2 : ℝ))
    have hL3 : HasDerivAt (fun t : ℝ => Real.log (t + 2) / 2) (1 / (2 * (x + 2))) x := by
      have h := (hg2.log hx3).div_const 2
      convert h using 1; field_simp [hx3]
    have hF := (hL1.sub hL2).add hL3
    convert hF using 1
    have h123 := mul_ne_zero (mul_ne_zero hx hx2) hx3
    field_simp [hx, hx2, hx3, h123]; ring
  · exact autodischarge_009_sympy_form x hx hx2 hx3
  · intro t ht ht3; exact form_disagree_009_equivalent t ht ht3

-- ============================================================
-- ADJUDICATION: x/(x⁴−1)  ∫ x/(x⁴-1) dx
-- FriCAS/Maxima: log(x-1)/4 + log(x+1)/4 - log(x²+1)/4   [factored]
-- SymPy:         log(x²-1)/4 - log(x²+1)/4                [product log]
-- Key lemma: Real.log_mul hx1 hx2  (x²-1 = (x-1)(x+1))
-- ============================================================

/-- The FriCAS/Maxima factored log form and the SymPy product log form are equal
    for x/(x⁴−1) under the same hypotheses HasDerivAt requires (x≠1, x≠−1). -/
theorem form_disagree_x_over_x4m1_equivalent (x : ℝ) (hx1 : x - 1 ≠ 0) (hx2 : x + 1 ≠ 0) :
    Real.log (x - 1) / 4 + Real.log (x + 1) / 4 - Real.log (x ^ 2 + 1) / 4 =
    Real.log (x ^ 2 - 1) / 4 - Real.log (x ^ 2 + 1) / 4 := by
  have hfact : x ^ 2 - 1 = (x - 1) * (x + 1) := by ring
  rw [hfact, Real.log_mul hx1 hx2]
  ring

/-- SymPy's product-form antiderivative for x/(x⁴-1), proved independently. -/
theorem autodischarge_x_over_x4m1_sympy_form (x : ℝ) (hx1 : x - 1 ≠ 0) (hx2 : x + 1 ≠ 0) :
    HasDerivAt (fun t : ℝ => Real.log (t ^ 2 - 1) / 4 - Real.log (t ^ 2 + 1) / 4)
               (x / (x ^ 4 - 1)) x := by
  have harg1 : x ^ 2 - 1 ≠ 0 := by
    have : x ^ 2 - 1 = (x - 1) * (x + 1) := by ring
    rw [this]; exact mul_ne_zero hx1 hx2
  have harg2 : (0 : ℝ) < x ^ 2 + 1 := by positivity
  have hpoly1 : HasDerivAt (fun t : ℝ => t ^ 2 - 1) (2 * x) x := by
    have h1 : HasDerivAt (fun t : ℝ => t ^ 2) (2 * x) x := by
      have h := hasDerivAt_pow 2 x; simpa [pow_one] using h
    have h2 : HasDerivAt (fun t : ℝ => (1 : ℝ)) 0 x := hasDerivAt_const x 1
    have h3 := h1.sub h2; simpa using h3
  have hpoly2 : HasDerivAt (fun t : ℝ => t ^ 2 + 1) (2 * x) x := by
    have h1 : HasDerivAt (fun t : ℝ => t ^ 2) (2 * x) x := by
      have h := hasDerivAt_pow 2 x; simpa [pow_one] using h
    have h2 : HasDerivAt (fun t : ℝ => (1 : ℝ)) 0 x := hasDerivAt_const x 1
    have h3 := h1.add h2; simpa using h3
  have hlog1 := (hpoly1.log harg1).div_const 4
  have hlog2 := (hpoly2.log harg2.ne').div_const 4
  have hF := hlog1.sub hlog2
  convert hF using 1
  have h4ne : x ^ 4 - 1 ≠ 0 := by
    have : x ^ 4 - 1 = (x ^ 2 - 1) * (x ^ 2 + 1) := by ring
    rw [this]; exact mul_ne_zero harg1 harg2.ne'
  field_simp [harg1, harg2.ne', h4ne]
  ring

-- ============================================================
-- ADJUDICATION: 1/(x·(x+1)·(x−1))
-- FriCAS/Maxima: −log(x) + log(x-1)/2 + log(x+1)/2   [factored]
-- SymPy:         −log(x) + log(x²-1)/2                [product log]
-- ============================================================

/-- The FriCAS/Maxima factored form and SymPy product form are equal
    for 1/(x(x+1)(x−1)) under x≠1, x≠−1. -/
theorem form_disagree_recip_xpolesym_equivalent (x : ℝ) (hx1 : x - 1 ≠ 0) (hx2 : x + 1 ≠ 0) :
    -Real.log x + Real.log (x - 1) / 2 + Real.log (x + 1) / 2 =
    -Real.log x + Real.log (x ^ 2 - 1) / 2 := by
  have hfact : x ^ 2 - 1 = (x - 1) * (x + 1) := by ring
  rw [hfact, Real.log_mul hx1 hx2]
  ring

/-- SymPy's product-form antiderivative for 1/(x(x+1)(x−1)), proved independently. -/
theorem autodischarge_recip_xpolesym_sympy_form (x : ℝ) (hx : x ≠ 0)
    (hx1 : x - 1 ≠ 0) (hx2 : x + 1 ≠ 0) :
    HasDerivAt (fun t : ℝ => -Real.log t + Real.log (t ^ 2 - 1) / 2)
               (1 / (x * (x + 1) * (x - 1))) x := by
  have harg : x ^ 2 - 1 ≠ 0 := by
    have : x ^ 2 - 1 = (x - 1) * (x + 1) := by ring
    rw [this]; exact mul_ne_zero hx1 hx2
  have hlogx : HasDerivAt (fun t : ℝ => -Real.log t) (-(1 / x)) x := by
    have h := (hasDerivAt_id x).log hx
    have hn := h.neg
    convert hn using 1; field_simp [hx]
  have hpoly : HasDerivAt (fun t : ℝ => t ^ 2 - 1) (2 * x) x := by
    have h1 : HasDerivAt (fun t : ℝ => t ^ 2) (2 * x) x := by
      have h := hasDerivAt_pow 2 x; simpa [pow_one] using h
    have h2 : HasDerivAt (fun t : ℝ => (1 : ℝ)) 0 x := hasDerivAt_const x 1
    have h3 := h1.sub h2; simpa using h3
  have hlog2 := (hpoly.log harg).div_const 2
  have hF := hlogx.add hlog2
  convert hF using 1
  have h3 : x * (x + 1) * (x - 1) ≠ 0 := mul_ne_zero (mul_ne_zero hx hx2) hx1
  field_simp [hx, harg, h3]
  rw [show x ^ 2 - 1 = (x - 1) * (x + 1) from by ring]
  ring

end
