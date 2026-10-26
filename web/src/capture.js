import { toJpeg } from 'html-to-image'

const PAD = 8
const HIDDEN = ['marker-layer', 'board-tools', 'flying-marker', 'flying-eraser']

export function captureArea(feed, box) {
  const rect = feed.getBoundingClientRect()
  const x = Math.max(0, Math.round(box.left - rect.left + feed.scrollLeft - PAD))
  const y = Math.max(0, Math.round(box.top - rect.top + feed.scrollTop - PAD))
  const bg = getComputedStyle(feed).backgroundColor
  return toJpeg(feed, {
    quality: 0.85,
    pixelRatio: Math.min(2, window.devicePixelRatio || 1),
    width: Math.round(box.right - box.left + 2 * PAD),
    height: Math.round(box.bottom - box.top + 2 * PAD),
    backgroundColor: bg && bg !== 'rgba(0, 0, 0, 0)' ? bg : '#ffffff',
    filter: (node) => !HIDDEN.some((c) => node.classList?.contains(c)),
    style: {
      transform: `translate(${-x}px, ${-y}px)`, transformOrigin: 'top left', margin: '0',
      height: `${feed.scrollHeight + 2 * feed.clientTop}px`, maxHeight: 'none', overflow: 'visible',
    },
  })
}
