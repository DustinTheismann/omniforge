(* Kernel-checked Coq half of the cross-prover certificate (Tier 8.1/8.2).
   Library: Coquelicot 3.x (https://coquelicot.saclay.inria.fr/).
   Every theorem below is accepted by coqc + Coquelicot; the CI job
   .github/workflows/coq.yml runs coqc on this file.

   IMPORTANT — branch cut, empirically confirmed by the Coq kernel:
   Coq's `ln` is the PRINCIPAL branch, differentiable only where its argument
   is > 0.  So the log cases carry `0 < arg` hypotheses, NOT the `arg <> 0`
   that Lean's total `Real.log` uses.  The two provers therefore prove the
   SAME equation under DIFFERENT domains for the branch-cut cases (007/005/008/009),
   and the SAME unconditional statement for the positive-argument cases
   (001/003/004/006).  Only the latter yield a caveat-free cross-prover
   certificate; the former are honest evidence of the branch-cut discrepancy
   this project studies. *)

Require Import Reals Coquelicot.Coquelicot.
Require Import Lra Lia Psatz.
Open Scope R_scope.

(* === Positive-argument cases: unconditional in BOTH Lean and Coq === *)

(* Claim 001 | COMPLEX_SUM | arg x^2+1 > 0 everywhere *)
Theorem coq_autodischarge_001 (x : R) :
  is_derive (fun x => ln (x ^ 2 + 1) ^ 2 / 2 + x ^ 2 / 2 - ln (x ^ 2 + 1) / 2) x
            ((2 * x * ln (x ^ 2 + 1) + x ^ 3) / (x ^ 2 + 1)).
Proof.
  auto_derive.
  - repeat split; nra.
  - replace (x * (x * 1) + 1) with (x ^ 2 + 1) by ring. field. nra.
Qed.

(* Claim 003 | LOG_POS_QUAD | arg x^2+1 > 0 everywhere *)
Theorem coq_autodischarge_003 (x : R) :
  is_derive (fun x => ln (x ^ 2 + 1) / 2) x (x / (x ^ 2 + 1)).
Proof. auto_derive. nra. field. nra. Qed.

(* Claim 004 | ARCTAN_POW | arctan total *)
Theorem coq_autodischarge_004 (x : R) :
  is_derive (fun x => atan (x ^ 2)) x (2 * x / (1 + x ^ 4)).
Proof. auto_derive. trivial. field. nra. Qed.

(* Claim 006 | ARCTAN_LINEAR | arctan total *)
Theorem coq_autodischarge_006 (x : R) :
  is_derive (fun x => atan (x + 1)) x (1 / (x ^ 2 + 2 * x + 2)).
Proof. auto_derive. trivial. field. nra. Qed.

(* === Branch-cut cases: Coq's principal-branch ln needs 0 < arg === *)

(* Claim 007 | LOG_SIMPLE | Coq: 0 < x   (Lean: x <> 0) *)
Theorem coq_autodischarge_007 (x : R) (hx : 0 < x) :
  is_derive (fun x => ln x) x (1 / x).
Proof. auto_derive. exact hx. field. lra. Qed.

(* Claim 008 | LOG_NEG_QUAD | Coq: 0 < x^2-4   (Lean: x^2-4 <> 0) *)
Theorem coq_autodischarge_008 (x : R) (hx : 0 < x ^ 2 - 4) :
  is_derive (fun x => ln (x ^ 2 - 4) / 2) x (x / (x ^ 2 - 4)).
Proof. auto_derive. exact hx. field. lra. Qed.

(* Claim 005 | LOG_PFD 2-pole | Coq: 0 < x, 0 < x+2 *)
Theorem coq_autodischarge_005 (x : R) (hx : 0 < x) (hx2 : 0 < x + 2) :
  is_derive (fun x => ln x / 2 + ln (x + 2) / 2) x ((x + 1) / (x * (x + 2))).
Proof. auto_derive. repeat split; lra. field. lra. Qed.

(* Claim 009 | LOG_PFD 3-pole | Coq: 0 < x, 0 < x+1, 0 < x+2 *)
Theorem coq_autodischarge_009 (x : R) (hx : 0 < x) (hx1 : 0 < x + 1) (hx2 : 0 < x + 2) :
  is_derive (fun x => ln x / 2 - ln (x + 1) + ln (x + 2) / 2) x
            (1 / (x * (x + 1) * (x + 2))).
Proof. auto_derive. repeat split; lra. field. lra. Qed.

(* end of generated file *)
