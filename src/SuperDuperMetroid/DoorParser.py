from SuperDuperMetroid.SM_Room_Header_Data import SuperMetroidRooms
from SuperDuperMetroid.hexhelper import HexHelper
import os


class DoorParser:
    # Crawls through each room's MDB to get the address of every door's DDB entry.
    # Addresses are relative to bank $83.
    # File provided should be opened in binary read format,
    @staticmethod
    def getDoorPointers(f):
        mdbAddressList = sorted(SuperMetroidRooms.addrToNumDoors)
        allDoorAddressesByRoomDict = {}
        for mdbAddress in mdbAddressList:
            f.seek(HexHelper.hexToInt(mdbAddress))
            doorsInRoom = []
            # Seek to where the doorout pointer is stored.
            f.seek(9, 1)
            # This is the pointer relative to bank $8F
            doorOutPointer = HexHelper.reverseEndianness(HexHelper.dataToHex(f.read(2)))
            f.seek(HexHelper.hexToInt("070000") + HexHelper.hexToInt(doorOutPointer))
            # We're now at the door pointers.
            # Reference our Room Header Data to see how many doors are in this room,
            # And read that many door pointers into our list.
            for i in range(SuperMetroidRooms.addrToNumDoors[mdbAddress]):
                doorsInRoom.append(HexHelper.reverseEndianness(HexHelper.dataToHex(f.read(2))))
            print(f"{SuperMetroidRooms.addrToRoomNameDict[mdbAddress]} ({mdbAddress})")
            for door in doorsInRoom:
                print(f"\t{door}")
            allDoorAddressesByRoomDict[mdbAddress] = doorsInRoom
        return allDoorAddressesByRoomDict


if __name__ == "__main__":
    # Build in this to make it faster to run.
    # Saves me some time.
    if os.path.isfile(os.getcwd() + "\\romfilepath.txt"):
        f = open(os.getcwd() + "\\romfilepath.txt", "r")
        filePath = f.readline().rstrip()
        f.close()
    else:
        print(
            "Enter full file path for your headerless Super Metroid ROM file.\nNote that the patcher DOES NOT COPY the game files - it will DIRECTLY OVERWRITE them. Make sure to create a backup before using this program.\nWARNING: Video game piracy is a crime - only use legally obtained copies of the game Super Metroid with this program."
        )
        filePath = input()
    f = open(filePath, "rb", buffering=0)
    DoorParser.getDoorPointers(f)
