def dataToHex(bytesToConvert):
    return bytesToConvert.hex

class DoorRegion:
    self.regionName = None
    self.startAddress = None
    self.roomList = []
    def __init__(self, regionName, startAddress):
        self.regionName = regionName
        self.startAddress = startAddress
    def addRoom(self, room):
        self.roomList += room
    

class DoorRoom:
    self.roomName
    self.startAddress
    self.numDoors
    self.doorsList
    __init__(self, roomName, startAddress, numDoors, f):
        self.roomName = roomName
        self.startAddress = startAddress
        self.numDoors = numDoors
        self.doorsList = doorsList
        currentFileAddress = "01" + startAddress
        for i in numDoors:
            self.doorsList.append(Door(currentFileAddress, f))
            currentFileAddress = intToHex(hexToInt(currentFileAddress) + 12)

class Door:
    self.address = None
    self.data = None
    __init__(self, fileAddress, f):
        self.address = fileAddress[=4:]
        f.seek(hexToInt(fileAddress))
        self.data = dataToHex(f.read(12))