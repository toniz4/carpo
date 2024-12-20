import pcbnew
import ezdxf
import numpy
import math

from ezdxf import transform
from pcbnew import FromMM

board = pcbnew.GetBoard()

# print(dir(board))

# filename = "/Users/cassio/Source/keyboards/carpo/pcb/board.py"
# exec(compile(open(filename, "rb").read(), filename, 'exec'))

# dxf = ezdxf.readfile("/Users/cassio/Source/keyboards/carpo/pcb/shape.dxf")

class Position:
    def __init__(self, board, origin=None):
        if not origin:
            origin = board.GetDesignSettings().GetGridOrigin()
        x, y = origin
        self.origin = (x, y)
        self.x = 0
        self.y = 0

    def setPos(self, x, y):
        x = x.item() if isinstance(x, numpy.float64) else x
        y = y.item() if isinstance(y, numpy.float64) else y
        self.x = self.origin[0] + FromMM(x)
        self.y = self.origin[1] - FromMM(y)

    def translate(self, x, y):
        self.x = self.x + FromMM(x)
        self.y = self.y - FromMM(y)

    def translatePolar(self, r, theta):
        x = r * math.cos(math.radians(theta))
        y = r * math.sin(math.radians(theta))
        self.x = self.x + FromMM(x)
        self.y = self.y - FromMM(y)

    def toVector2I(self):
        return pcbnew.VECTOR2I(self.x, self.y)

    def toWxPoint(self):
        return pcbnew.wxPoint((self.x, self.y))

class Shape:
    def __init__(self, board, layer):
        self.board = board
        self.layer = layer

    def __bulgeToArc(self, start, end, bulge):
        return ezdxf.math.bulge_to_arc(start, end, bulge)

    def shape(self):
        shape = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        shape.SetLayer(self.layer)
        self.board.Add(shape)
        return shape

    def line(self, start, end):
        shape = self.shape()
        shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        posStart = Position(self.board)
        posEnd = Position(self.board)

        posStart.setPos(start[0], start[1])
        posEnd.setPos(end[0], end[1])

        shape.SetStart(posStart.toVector2I())
        shape.SetEnd(posEnd.toVector2I())

    def arc(self, center, start, end):
        shape = self.shape()
        shape.SetShape(pcbnew.SHAPE_T_ARC)
        posStart = Position(self.board)
        posEnd = Position(self.board)
        posCenter = Position(self.board)

        posStart.setPos(start[0], start[1])
        posEnd.setPos(end[0], end[1])
        posCenter.setPos(center[0], center[1])

        shape.SetStart(posStart.toVector2I())
        shape.SetEnd(posEnd.toVector2I())
        shape.SetCenter(posCenter.toVector2I())

    def __lineOrArc(self, start, end):
        bulge = start[4]
        if bulge != 0:
            arc = self.__bulgeToArc((start[0], start[1]), (end[0], end[1]), start[4])
            if bulge > 0:
                self.arc(arc[0], end, start)
            else:
                self.arc(arc[0], start, end)
        else:
            self.line(start, end)

    def poly(self, points):
        firstPt = points[0]
        prevPt = points[0]
        for curPt in points[1:]:
            self.__lineOrArc(prevPt, curPt)
            prevPt = curPt
        self.__lineOrArc(prevPt, firstPt)

def clearOutlines(board):
    pass
    # for item in board.GetDrawings():
    #     if type(item) is pcbnew.PCB_SHAPE and item.GetLayer() == pcbnew.Edge_Cuts:
    #         board.Remove(item)

def makeOutline(board, msp):
    clearOutlines(board)
    mountingHoles = ["H" + str(i) for i in range(5)]
    for entity in msp:
        if type(entity) == ezdxf.entities.lwpolyline.LWPolyline:
            shape = Shape(board, pcbnew.Edge_Cuts)
            shape.poly(entity)
        elif type(entity) == ezdxf.entities.line.Line:
            shape = Shape(board, pcbnew.Edge_Cuts)
            shape.line(entity.dxf.start, entity.dxf.end)
        elif type(entity) == ezdxf.entities.arc.Arc:
            shape = Shape(board, pcbnew.Edge_Cuts)
            shape.arc(entity.dxf.center, entity.end_point, entity.start_point)
        elif type(entity) == ezdxf.entities.circle.Circle:
            position = Position(board)
            x, y, _ = entity.dxf.center
            position.setPos(x, y)
            placeFootprint(mountingHoles.pop(), position, 0, False)
        else:
            print(f'unhandled {entity}')

def midpoint(x1, y1, x2, y2):
    return ((x1 + x2)/2, (y1 + y2)/2)

def angleLine(p1, p2):
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    rad = math.atan2(dy, dx)
    deg = math.degrees(rad)
    return deg if deg != 180 else 0

def sortByY(line):
    start, end = line if line[0][1] > line[1][1] else line[::-1]
    return start[0]

def sortByX(point):
    return (point[0] + point[1]) * -1

def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def isPointInLine(line, point):
    result = (distance(line[0], point) + distance(point, line[1])) - distance(line[1], line[0])
    return result < 1

def placeFootprint(label, pos, orient, flip):
    fp = board.FindFootprintByReference(label)
    flipped = fp.IsFlipped()
    if flip and not flipped:
        fp.Flip(fp.GetCenter(), True)
    fp.SetOrientationDegrees(orient if not flip else orient + 180)
    fp.SetPosition(pos.toVector2I())

def rotateAll(board):
    for f in board.GetFootprints():
        a = f.GetOrientationDegrees()
        p = f.GetPosition()
        f.Flip(f.GetCenter(), True)
        f.SetOrientationDegrees(180 + a)
        f.SetPosition(p)
    pcbnew.Refresh()

class Switches:
    def __init__(self):
        self.__switches = dict()

    def __getitem__(self, key):
        return self.__switches[key]

    def __iter__(self):
        return iter(self.__switches)

    def addSwitch(self, label, pos, orientation):
        self.__switches[label] = (pos, orientation)


def getSwitchPositions(dxf):
    column_switches = [["SW" + str(j + i) for i in range(1, 16, 5)] for j in range(5)]
    thumb_switches = ["SW" + str(i) for i in range(16, 19)]

    switches = Switches()

    positions = []
    control_lines = []

    for entity in dxf.modelspace():
        if type(entity) == ezdxf.entities.line.Line:
            pstart = entity.dxf.start
            pend = entity.dxf.end
            mid = midpoint(pstart[0], pstart[1], pend[0], pend[1])
            lenght = math.hypot(pstart[0] - pend[0], pstart[1] - pend[1])
            if lenght > 18.1 * 1.5:
                control_lines.append((pstart, pend))
            else:
                positions.append((mid, (entity.dxf.start, entity.dxf.end)))

    control_lines.sort(key=sortByY)
    positions.sort(key=lambda x : sortByX(x[0]))

    for ctrl, ref in zip(control_lines, column_switches):
        column = []
        for (p, l) in positions:
            if isPointInLine(ctrl, p):
                column.append((p, l))
        for (label, (p, line)) in zip(ref, column):
            orientation = angleLine(line[1], line[0])
            position = Position(board)
            position.setPos(p[0], p[1])
            switches.addSwitch(label, position, orientation)
            # placeFootprint(label, p, orientation, True)
            positions.remove((p, line))

    for (label, (p, l)) in zip(thumb_switches, positions[::-1]):
        orientation = angleLine(l[1], l[0])
        position = Position(board)
        position.setPos(p[0], p[1])
        switches.addSwitch(label, position, orientation)
        # placeFootprint(label, p, orientation, True)

    return switches

def placeSwitches(switches):
    for k in switches:
        pos, orientation = switches[k]
        placeFootprint(k, pos, orientation, True)

def placeDiodes(switches):
    for k in switches:
        label = "D" + k[2:]
        position, orientation = switches[k]
        position.translatePolar(7.341, (142.2) + orientation)
        placeFootprint(label, position, orientation + 90, True)

# pcbOutline = ezdxf.readfile("/Users/cassio/Source/keyboards/carpo/pcb/pcb.dxf")
# pcbOutlineModel = pcbOutline.modelspace()
# transform.z_rotate(pcbOutlineModel, math.pi)

# makeOutline(board, pcbOutlineModel)

switchPos = ezdxf.readfile("/Users/cassio/Source/keyboards/carpo/pcb/switch_pos.dxf")
switches = getSwitchPositions(switchPos)

# placeSwitches(switches)
# placeDiodes(switches)
# makeOutline(switchPos.modelspace())
print('done')

pcbnew.Refresh()
