// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useAsyncData } from "./use-async-data";

afterEach(cleanup);

describe("analysis page refresh requests", () => {
  it("keeps a completed refresh when an older loading request resolves later", async () => {
    const resolves: Array<(value: string) => void> = [];
    const fetcher = () => new Promise<string>((resolve) => resolves.push(resolve));
    const { result } = renderHook(() => useAsyncData(fetcher, []));
    act(() => result.current.refresh());
    await act(async () => resolves[1]("parsed"));
    await waitFor(() => expect(result.current.data).toBe("parsed"));
    await act(async () => resolves[0]("processing"));
    expect(result.current.data).toBe("parsed");
  });
});
