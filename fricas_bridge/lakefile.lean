import Lake
open Lake DSL

package "fricas_bridge" where
  name := "fricas_bridge"

require "leanprover-community" / "mathlib" @ git "v4.30.0"

/-- The verified Risch integration library.
    Contains RischVerification.lean with four HasDerivAt theorems
    and the fricas_integrate pipeline. -/
lean_lib FriCASBridge where
  roots := #[`RischVerification]
