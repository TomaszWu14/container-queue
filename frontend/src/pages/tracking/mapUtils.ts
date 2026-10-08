/**
 * Trasa statku przecinająca antymerydian (180°/-180°) rysowana jako jedna polilinia
 * dałaby fałszywą linię w poprzek całej mapy. Dzielimy trasę na segmenty w każdym
 * miejscu, gdzie skok długości geograficznej między kolejnymi punktami przekracza 180°.
 */
export function splitTrailSegments<T extends [number, number]>(points: T[]): T[][] {
  if (points.length === 0) return []
  const segments: T[][] = [[points[0]]]
  for (let i = 1; i < points.length; i++) {
    const prevLon = points[i - 1][1]
    const lon = points[i][1]
    if (Math.abs(lon - prevLon) > 180) segments.push([])
    segments[segments.length - 1].push(points[i])
  }
  return segments.filter(seg => seg.length > 0)
}
