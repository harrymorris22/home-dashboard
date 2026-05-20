import { useEffect } from "react";

import { Card } from "../../_shared/Card";

/** Climate detail = redirect to full loft.harrymorris.me PWA.
 * Tile tap normally calls window.open() directly, but if a user lands on
 * /widget/climate via deep-link, redirect them out. */
export function ClimateDetail() {
  useEffect(() => {
    window.location.href = "https://loft.harrymorris.me/";
  }, []);

  return (
    <Card>
      <p className="text-secondary">Opening climate dashboard…</p>
      <p className="text-xs text-secondary mt-2">
        If nothing happens, <a className="text-primary underline" href="https://loft.harrymorris.me/">open it directly</a>.
      </p>
    </Card>
  );
}
