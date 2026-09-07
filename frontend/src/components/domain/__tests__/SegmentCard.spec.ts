import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"

import SegmentCard from "@/components/domain/SegmentCard.vue"
import { i18n } from "@/locales"
import type { Segment } from "@/api/types"

function makeSegment(overrides: Partial<Segment> = {}): Segment {
  return {
    index: 0,
    title: "Hook A",
    status: "cut",
    score: 87,
    duration: 33.9,
    hook: "Hello world",
    reasoning: "open",
    start_time: 10.0,
    end_time: 43.9,
    ...overrides,
  } as Segment
}

describe("SegmentCard (compõe shadcn-vue)", () => {
  it("renders title and score", () => {
    const wrapper = mount(SegmentCard, {
      props: { segment: makeSegment() },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain("Hook A")
    expect(wrapper.text()).toContain("87/100")
  })

  it("renders hook and reasoning", () => {
    const wrapper = mount(SegmentCard, {
      props: { segment: makeSegment() },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain("Hello world")
    expect(wrapper.text()).toContain("open")
  })

  it("renders timestamps", () => {
    const wrapper = mount(SegmentCard, {
      props: { segment: makeSegment() },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain("10.0s")
    expect(wrapper.text()).toContain("43.9s")
  })

  it("renders a progress bar (shadcn Progress) via data-slot", () => {
    const wrapper = mount(SegmentCard, {
      props: { segment: makeSegment() },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('[data-slot="card"]').exists()).toBe(true)
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(true)
  })
})
