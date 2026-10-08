"""Exact planar segment/bulge geometry and bounded sweep broad-phase, no dependencies."""

import math
from dataclasses import dataclass

from ..core.exceptions import CadError

EPS = 1e-9


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def same(a, b):
    """Connectivity is exact; tolerance is reserved for near-connection candidates."""
    return tuple(a[:2]) == tuple(b[:2])


@dataclass(frozen=True)
class Segment:
    start: tuple[float, float]
    end: tuple[float, float]
    bulge: float = 0

    @property
    def arc(self):
        if self.bulge == 0:
            return None
        dx, dy = sub(self.end, self.start)
        b = self.bulge
        center = (
            (self.start[0] + self.end[0]) / 2 - dy * (1 - b * b) / (4 * b),
            (self.start[1] + self.end[1]) / 2 + dx * (1 - b * b) / (4 * b),
        )
        radius = math.hypot(dx, dy) * (1 + b * b) / (4 * abs(b))
        angle = math.atan2(self.start[1] - center[1], self.start[0] - center[0])
        return center, radius, angle, 4 * math.atan(b)

    def contains_angle(self, angle):
        _, _, start, sweep = self.arc
        distance = (angle - start) % math.tau if sweep > 0 else (start - angle) % math.tau
        return distance <= abs(sweep) + EPS or abs(distance - math.tau) <= EPS

    @property
    def length(self):
        return self.arc[1] * abs(self.arc[3]) if self.arc else math.dist(self.start, self.end)

    @property
    def bounds(self):
        points = [self.start, self.end]
        if self.arc:
            center, radius, _, _ = self.arc
            for angle in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                if self.contains_angle(angle):
                    points.append(
                        (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))
                    )
        return (
            min(p[0] for p in points),
            min(p[1] for p in points),
            max(p[0] for p in points),
            max(p[1] for p in points),
        )

    def distance(self, point):
        if self.arc:
            center, radius, _, _ = self.arc
            angle = math.atan2(point[1] - center[1], point[0] - center[0])
            if self.contains_angle(angle):
                return abs(math.dist(point[:2], center) - radius)
            return min(math.dist(point[:2], self.start), math.dist(point[:2], self.end))
        delta = sub(self.end, self.start)
        denominator = delta[0] ** 2 + delta[1] ** 2
        if denominator == 0:
            return math.dist(point[:2], self.start)
        parameter = (
            sum(x * y for x, y in zip(sub(point, self.start), delta, strict=True)) / denominator
        )
        parameter = max(0, min(1, parameter))
        closest = (self.start[0] + parameter * delta[0], self.start[1] + parameter * delta[1])
        return math.dist(point[:2], closest)


def segments(pipe):
    points = [tuple(p[:2]) for p in pipe["vertices"]]
    ends = points[1:] + ([points[0]] if pipe["closed"] else [])
    bulges = pipe.get("bulges", [])
    return [
        Segment(a, b, bulges[i] if i < len(bulges) else 0)
        for i, (a, b) in enumerate(zip(points, ends, strict=False))
    ]


def bounds(pipe):
    boxes = [s.bounds for s in segments(pipe)]
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def boxes_overlap(first, second):
    return (
        first[0] <= second[2] + EPS
        and second[0] <= first[2] + EPS
        and first[1] <= second[3] + EPS
        and second[1] <= first[3] + EPS
    )


def broad_pairs(boxes, budget=10000):
    """Sweep in X, prune in Y; fail explicitly in dense pathological drawings."""
    active = []
    emitted = 0
    comparisons = 0
    for index in sorted(range(len(boxes)), key=lambda i: boxes[i][0]):
        box = boxes[index]
        active = [j for j in active if boxes[j][2] + EPS >= box[0]]
        for other in active:
            comparisons += 1
            if comparisons > budget:
                raise CadError("Geometry comparison budget exceeded; narrow the layer/region")
            if boxes_overlap(box, boxes[other]):
                emitted += 1
                if emitted > budget:
                    raise CadError("Geometry pair budget exceeded; narrow the layer/region")
                yield min(index, other), max(index, other)
        active.append(index)


def _on_arc(segment, point):
    center, _, _, _ = segment.arc
    return segment.contains_angle(math.atan2(point[1] - center[1], point[0] - center[0]))


def intersections(first: Segment, second: Segment):
    """Finite line/arc intersections, including overlap boundary points."""
    if first.arc is None and second.arc is None:
        r, s = sub(first.end, first.start), sub(second.end, second.start)
        delta = sub(second.start, first.start)
        divisor = cross(r, s)
        if abs(divisor) <= EPS:
            if abs(cross(delta, r)) > EPS:
                return []
            return unique(
                [
                    p
                    for p in (first.start, first.end, second.start, second.end)
                    if first.distance(p) <= EPS and second.distance(p) <= EPS
                ]
            )
        t, u = cross(delta, s) / divisor, cross(delta, r) / divisor
        if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
            return [(first.start[0] + t * r[0], first.start[1] + t * r[1])]
        return []
    if first.arc is None or second.arc is None:
        line, arc = (first, second) if first.arc is None else (second, first)
        center, radius, _, _ = arc.arc
        delta, origin = sub(line.end, line.start), sub(line.start, center)
        a = sum(v * v for v in delta)
        if a == 0:
            return (
                [line.start]
                if abs(math.dist(line.start, center) - radius) <= EPS and _on_arc(arc, line.start)
                else []
            )
        b = 2 * sum(x * y for x, y in zip(origin, delta, strict=True))
        c = sum(v * v for v in origin) - radius * radius
        discriminant = b * b - 4 * a * c
        if discriminant < -EPS:
            return []
        points = []
        for t in (
            (-b - math.sqrt(max(0, discriminant))) / (2 * a),
            (-b + math.sqrt(max(0, discriminant))) / (2 * a),
        ):
            point = (line.start[0] + t * delta[0], line.start[1] + t * delta[1])
            if -EPS <= t <= 1 + EPS and _on_arc(arc, point):
                points.append(point)
        return unique(points)
    c1, r1, _, _ = first.arc
    c2, r2, _, _ = second.arc
    distance = math.dist(c1, c2)
    if distance <= EPS:
        return unique(
            [
                p
                for p in (first.start, first.end, second.start, second.end)
                if abs(r1 - r2) <= EPS and _on_arc(first, p) and _on_arc(second, p)
            ]
        )
    if distance > r1 + r2 + EPS or distance < abs(r1 - r2) - EPS:
        return []
    along = (r1 * r1 - r2 * r2 + distance * distance) / (2 * distance)
    height = math.sqrt(max(0, r1 * r1 - along * along))
    ux, uy = (c2[0] - c1[0]) / distance, (c2[1] - c1[1]) / distance
    base = (c1[0] + along * ux, c1[1] + along * uy)
    points = [
        (base[0] - height * uy, base[1] + height * ux),
        (base[0] + height * uy, base[1] - height * ux),
    ]
    return unique([p for p in points if _on_arc(first, p) and _on_arc(second, p)])


def unique(points):
    result = []
    for point in points:
        if not any(math.dist(point, other) <= EPS for other in result):
            result.append(point)
    return result


def pipe_intersections(first, second, budget=10000):
    first_segments, second_segments = segments(first), segments(second)
    combined = first_segments + second_segments
    points = []
    split = len(first_segments)
    for i, j in broad_pairs([s.bounds for s in combined], budget):
        if i < split <= j:
            points.extend(intersections(combined[i], combined[j]))
    return unique(points)
