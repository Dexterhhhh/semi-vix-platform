import { describe, expect, it } from "vitest";

import type { SVIXPoint } from "./index";

describe("SVIX dashboard data contract", () => {
  it("accepts the current index payload used by the dashboard", () => {
    const payload: SVIXPoint = {
      timestamp: "2026-07-12T00:00:00Z",
      svix: 32.5,
      core: 29.4,
      memory: 48.2,
      ai: 35.1,
      calculation_quality: 1,
    };

    expect(payload.svix).toBeGreaterThan(0);
    expect(payload.memory).toBeGreaterThan(payload.svix);
  });
});
