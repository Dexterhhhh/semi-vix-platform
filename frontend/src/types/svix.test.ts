import { describe, expect, it } from "vitest";

import type { SvixCurrent } from "./index";

describe("SVIX dashboard data contract", () => {
  it("accepts the current index payload used by the dashboard", () => {
    const payload: SvixCurrent = {
      svix: 32.5,
      memory: 48.2,
      ai: 35.1,
    };

    expect(payload.svix).toBeGreaterThan(0);
    expect(payload.memory).toBeGreaterThan(payload.svix);
  });
});
