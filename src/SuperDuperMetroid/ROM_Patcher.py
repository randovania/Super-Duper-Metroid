# Super Duper Metroid - A Super Metroid Randomizer Placement Patcher
# Written by Samuel D. Roy
#
# Thanks to Metroid Construction for its detailed RAM and ROM maps.
# https://wiki.metroidconstruction.com/doku.php?id=super_metroid
#
# Thanks to Jathys for a plethora of miscellaneous additional documentation.
# Their work helped me decode a lot of the more in-depth game functionality.
# https://jathys.zophar.net/supermetroid/
#
# Thanks to Kazuto for their More Efficient Item PLMs Hacks.
# https://www.metroidconstruction.com/resource.php?id=349
#
# Thanks to PHOSPHOTiDYL for their Skip Intro Saves hack, which enables random save start.
# https://metroidconstruction.com/resource.php?id=265
#
# Designed for HEADERLESS ROMS ONLY!
#
# It is recommended to use a monospace font when reading this code.
# Many tables are formatted to take advantage of monospace fonts.
# I personally use OCRA.
#
# FOR DEVELOPERS:
#
# Breakdown of memory changes:
#
# Message Box code edits are made to 4 minor functions in bank 85.
# Bank 85 also has 4 more routines appended to the start of free space,
# Along with routines to replace pickup effects for game items.
# In bank 85, starting at $85:9A00, we write 5 tables to ROM, each 2 pages long.
# TODO: Shift tables forward to make room for more routines.
# Each entry in each table is 2 bytes long.
# For each item in the game, these point to, in order:
# * Pointer to Messagebox Header/Footer tilemap
# * Pointer to Messagebox Content tilemap
# * The size of the Messagebox content in memory
# * The messagebox ID, functionally equivalent to the value stored in RAM at $7E:1C1F
#   when the Messagebox code is being executed.
# * Pointer to the collection code to run for this item
#
# Item PLM References are overwritten with the appropriate new type in bank $8F
#
# RAM address $7FFF72-$7FFF73 is the routine in bank 83 to jump to.
# RAM address $7FFF74-$7FFF75 is nonzero when we haven't been sent an item.
# RAM address $7FFF76-$7FFF7F are occupied by values for a multiworld item we've been
# Given. Same as the 5 values we have tables for.
#
# RAM addresses $7FFF8E-$7FFFFF are occupied by a copy of the game's item bitflags,
# Which are used to determine which item a player has picked up.
#
# Kazuto's More Efficient PLMs patch is applied, and changes are present
# in banks $84 and $89.

import json
import os
from pathlib import Path

from SuperDuperMetroid.IPS_Patcher import IPSPatcher
from SuperDuperMetroid.SM_Constants import SuperMetroidConstants

VRAM_ITEMS_PATH = Path(__file__).with_name(name="VramItems.bin")


class MessageBoxGenerator:
    # List of characters that messages are allowed to have.
    # Note that messages will be converted to uppercase
    # Before removing invalid characters.
    allowedCharacterList = [
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
        "L",
        "M",
        "N",
        "O",
        "P",
        "Q",
        "R",
        "S",
        "T",
        "U",
        "V",
        "W",
        "X",
        "Y",
        "Z",
        "%",
        " ",
        "&",
        "-",
        ".",
        ",",
        "'",
        "?",
        "!",
    ]

    # First digit of tuple is row in tilemap, second is column.
    # The messagebox character tilemap is 16x16.
    characterToTilemapPosDict = {
        "1": (0, 0),
        "2": (0, 1),
        "3": (0, 2),
        "4": (0, 3),
        "5": (0, 4),
        "6": (0, 5),
        "7": (0, 6),
        "8": (0, 7),
        "9": (0, 8),
        "0": (0, 9),
        "%": (0, 10),
        " ": (4, 14),
        "&": (12, 8),
        "-": (12, 15),
        "A": (14, 0),
        "B": (14, 1),
        "C": (14, 2),
        "D": (14, 3),
        "E": (14, 4),
        "F": (14, 5),
        "G": (14, 6),
        "H": (14, 7),
        "I": (14, 8),
        "J": (14, 9),
        "K": (14, 10),
        "L": (14, 11),
        "M": (14, 12),
        "N": (14, 13),
        "O": (14, 14),
        "P": (14, 15),
        "Q": (15, 0),
        "R": (15, 1),
        "S": (15, 2),
        "T": (15, 3),
        "U": (15, 4),
        "V": (15, 5),
        "W": (15, 6),
        "X": (15, 7),
        "Y": (15, 8),
        "Z": (15, 9),
        ".": (15, 10),
        ",": (15, 11),
        "'": (15, 12),
        "?": (15, 14),
        "!": (15, 15),
    }

    maxMessageLengths = {"Small": 19, "Large": 26}

    # Maximum length in characters of a standard message box.
    # Technically some, like the missile pickup, are bigger, but we're ignoring those.
    messageBoxMaxLength = 19

    # Create the message box generator.
    # TODO: Place initial method *after* appended messagebox routines.
    def __init__(self, ROMFile, initialAddress="029643"):
        self.currentAddress = initialAddress
        self.messageBoxList = {}
        self.file = ROMFile
        self.smallMessagePointerTable = {}
        self.largeMessagePointerTable = {}

    # Change this message to be usable.
    def conformMessageToFormat(self, messageText, messageBoxSize):
        # First we convert the message to uppercase only.
        messageText = messageText.upper()

        # Now we strip out any characters that we can't have in our message.
        strippedMessage = ""
        for messageChar in messageText:
            if messageChar in self.allowedCharacterList:
                strippedMessage += messageChar
        # Tell the user if their message contains unsupported characters
        if len(messageText) > len(strippedMessage):
            print(
                "Warning Message box text "
                + messageText
                + " contains unsupported characters. These will be stripped from the message.\nMessage boxes support the latin alphabet (will be converted to uppercase only), the arabic numerals 0-9, spaces, and a limited set of miscellaneous characters: ?!,.'&-%"
            )
        messageText = strippedMessage

        # If the message is too long, cut it off.
        # We'll also include a warning if this happens.
        if len(messageText) > maxMessageLengths(messageBoxSize):
            print(
                f"Warning: Message box text {messageText} exceeds maximum length of message box. Message will be cut to first 19 characters."
            )
            messageText = messageText[: maxMessageLengths(messageBoxSize)]
        return messageText

    # Generate and write the hex of a line of message to the file.
    def generateMessagebox(self, messageText, messageBoxSize):
        messageText = self.conformMessageToFormat(messageText, messageBoxSize)

        # Get the raw text of the message.
        # Pad the message with spaces if it doesn't take up the whole line.
        numSpaces = maxMessageLengths(messageBoxSize) - len(messageText)
        actualMessageString = floor(numSpaces / 2) * " " + messageText
        numSpaces -= floor(numSpaces / 2)
        actualMessageString += " " * numSpaces

        # Convert our stuff to a hex string
        messageHex = ""
        for c in actualMessageString:
            indices = characterToTilemapPosDict[c]
            # Add the tile index byte
            messageHex += (hex(int(indices[0], 16))[2:]).upper()
            messageHex += (hex(int(indices[1], 16))[2:]).upper()
            # Add the metadata byte
            # We assume this character is unflipped and
            messageHex += "28"

        # Add padding for memory.
        # These tiles aren't drawn by the game but are part of the message
        # Each line of a messages is exactly 64 bytes long.
        # The bank where the game stores messages has room for exactly 270 lines of messages,
        # So it is impossible to run out of space even if every item belongs to a different,
        # Non-host player and each is a unique item not present in the vanilla game,
        # Assuming only one-line messages were used.
        paddingHex = "0E00"
        if messageBoxSize == "Small":
            messagHex = (paddingHex * 6) + messageHex + (paddingHex * 7)
        elif messageBoxSize == "Large":
            messagHex = (paddingHex * 3) + messageHex + (paddingHex * 3)
        else:
            print(
                f"Warning: You are attempting to create a message with size paramater {messageBoxSize}, which is not a supported size.\nSupported sizes are Small and Large"
            )
            return

        # Record our addition of this message.
        if messageBoxSize == "Small":
            if messageText in smallMessagePointerTable.keys():
                print(
                    f"Warning: The message {messageText} has already been added to this ROM.\nPlease consult the current maintainer of this patcher."
                )
            else:
                self.smallMessagePointerTable[messageText] = messageText
        elif messageBoxSize == "Large":
            if messageText in largeMessagePointerTable.keys():
                print(
                    f"Warning: The message {messageText} has already been added to this ROM.\nPlease consult the current maintainer of this patcher."
                )
            else:
                self.largeMessagePointerTable[messageText] = messageText

        # Write hex to ROM
        self.file.seek(int(self.currentAddress, 16))
        self.file.write(bytes.fromhex(format(messageHex, "x")))

        # Update address for next message box write.
        self.currentAddress = (hex(int(self.currentAddress, 16) + 64)[2:]).upper()
        # Prepend a 0 to make it look more presentable.
        # Not important, I'm just a perfectionist.
        if len(self.currentAddress) == 5:
            self.currentAddress = "0" + self.currentAddress


class ItemType:
    itemName = None
    GFXOffset = None
    # Most items use this all 00's palette, so just have it as the defaultl.
    paletteBytes = bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    def __init__(self, itemName, GFXOffset, paletteBytes=None):
        self.itemName = itemName
        self.GFXOffset = GFXOffset
        if paletteBytes is not None:
            self.paletteBytes = paletteBytes


# Class which represents items being passed to the game from the generator
# TODO: Implement this more fully
class PickupPlacementData:
    def __init__(
        self,
        quantityGiven,
        pickupIndex,
        itemName,
        pickupItemEffect="Default",
        nativeGraphics=True,
        ownerName=None,
        graphicsFileName=None,
        nativeSpriteName="Default",
    ):
        self.quantityGiven = quantityGiven
        self.pickupIndex = pickupIndex
        self.itemName = itemName
        self.pickupItemEffect = pickupItemEffect
        self.nativeGraphics = nativeGraphics
        self.ownerName = ownerName
        self.graphicsFileName = graphicsFileName
        self.nativeSpriteName = nativeSpriteName


def rawRandomizedExampleItemPickupData():
    return [
        PickupPlacementData(1, 0, "Grapple Beam"),
        PickupPlacementData(100, 1, "Reserve Tank"),
        PickupPlacementData(5, 2, "Missile Expansion"),
        PickupPlacementData(100, 3, "Energy Tank"),
        PickupPlacementData(5, 4, "Missile Expansion"),
        PickupPlacementData(5, 5, "Missile Expansion"),
        PickupPlacementData(5, 6, "Power Bomb Expansion"),
        PickupPlacementData(5, 7, "Missile Expansion"),
        PickupPlacementData(100, 8, "Energy Tank"),
        PickupPlacementData(5, 9, "Missile Expansion"),
        PickupPlacementData(5, 10, "Missile Expansion"),
        PickupPlacementData(5, 11, "Missile Expansion"),
        PickupPlacementData(5, 12, "Missile Expansion"),
        PickupPlacementData(100, 13, "Energy Tank"),
        PickupPlacementData(5, 14, "Super Missile Expansion"),
        PickupPlacementData(100, 15, "Energy Tank"),
        PickupPlacementData(100, 16, "Energy Tank"),
        PickupPlacementData(6, 17, "Missile Expansion"),
        PickupPlacementData(5, 18, "Super Missile Expansion"),
        PickupPlacementData(1, 19, "Spazer Beam"),
        PickupPlacementData(6, 21, "Missile Expansion"),
        PickupPlacementData(1, 22, "Speed Booster"),
        PickupPlacementData(100, 23, "Energy Tank"),
        PickupPlacementData(6, 24, "Missile Expansion"),
        PickupPlacementData(5, 25, "Super Missile Expansion"),
        PickupPlacementData(1, 26, "Morph Ball"),
        PickupPlacementData(6, 27, "Missile Expansion"),
        PickupPlacementData(1, 28, "Hi-Jump Boots"),
        PickupPlacementData(6, 29, "Missile Expansion"),
        PickupPlacementData(6, 30, "Missile Expansion"),
        PickupPlacementData(5, 31, "Power Bomb Expansion"),
        PickupPlacementData(100, 33, "Reserve Tank"),
        PickupPlacementData(1, 34, "Morph Ball Bombs"),
        PickupPlacementData(6, 35, "Missile Expansion"),
        PickupPlacementData(100, 36, "Energy Tank"),
        PickupPlacementData(5, 37, "Power Bomb Expansion"),
        PickupPlacementData(1, 38, "Plasma Beam"),
        PickupPlacementData(5, 39, "Super Missile Expansion"),
        PickupPlacementData(5, 40, "Super Missile Expansion"),
        PickupPlacementData(6, 41, "Missile Expansion"),
        PickupPlacementData(6, 42, "Missile Expansion"),
        PickupPlacementData(6, 43, "Missile Expansion"),
        PickupPlacementData(5, 44, "Power Bomb Expansion"),
        PickupPlacementData(100, 48, "Energy Tank"),
        PickupPlacementData(6, 49, "Missile Expansion"),
        PickupPlacementData(5, 50, "Power Bomb Expansion"),
        PickupPlacementData(6, 51, "Missile Expansion"),
        PickupPlacementData(1, 52, "X-Ray Scope"),
        PickupPlacementData(1, 53, "Space Jump"),
        PickupPlacementData(6, 54, "Missile Expansion"),
        PickupPlacementData(1, 55, "Varia Suit"),
        PickupPlacementData(5, 56, "Missile Expansion"),
        PickupPlacementData(5, 57, "Missile Expansion"),
        PickupPlacementData(5, 58, "Super Missile Expansion"),
        PickupPlacementData(5, 59, "Missile Expansion"),
        PickupPlacementData(1, 60, "Screw Attack"),
        PickupPlacementData(100, 61, "Energy Tank"),
        PickupPlacementData(5, 62, "Power Bomb Expansion"),
        PickupPlacementData(6, 63, "Missile Expansion"),
        PickupPlacementData(100, 64, "Reserve Tank"),
        PickupPlacementData(1, 65, "Gravity Suit"),
        PickupPlacementData(5, 66, "Missile Expansion"),
        PickupPlacementData(5, 67, "Super Missile Expansion"),
        PickupPlacementData(1, 68, "Ice Beam"),
        PickupPlacementData(100, 70, "Energy Tank"),
        PickupPlacementData(5, 71, "Missile Expansion"),
        PickupPlacementData(6, 73, "Missile Expansion"),
        PickupPlacementData(5, 74, "Missile Expansion"),
        PickupPlacementData(5, 75, "Power Bomb Expansion"),
        PickupPlacementData(100, 76, "Energy Tank"),
        PickupPlacementData(5, 77, "Power Bomb Expansion"),
        PickupPlacementData(5, 78, "Missile Expansion"),
        PickupPlacementData(5, 79, "Missile Expansion"),
        PickupPlacementData(5, 80, "Missile Expansion"),
        PickupPlacementData(5, 128, "Super Missile Expansion"),
        PickupPlacementData(5, 129, "Missile Expansion"),
        PickupPlacementData(1, 130, "Charge Beam"),
        PickupPlacementData(5, 131, "Missile Expansion"),
        PickupPlacementData(5, 132, "Power Bomb Expansion"),
        PickupPlacementData(5, 133, "Missile Expansion"),
        PickupPlacementData(5, 134, "Missile Expansion"),
        PickupPlacementData(1, 135, "Spring Ball"),
        PickupPlacementData(6, 136, "Missile Expansion"),
        PickupPlacementData(6, 137, "Missile Expansion"),
        PickupPlacementData(100, 138, "Reserve Tank"),
        PickupPlacementData(100, 139, "Energy Tank"),
        PickupPlacementData(5, 140, "Super Missile Expansion"),
        PickupPlacementData(1, 141, "Wave Beam"),
        PickupPlacementData(6, 142, "Missile Expansion"),
        PickupPlacementData(100, 143, "Energy Tank"),
        PickupPlacementData(5, 144, "Power Bomb Expansion"),
        PickupPlacementData(5, 145, "Super Missile Expansion"),
        PickupPlacementData(6, 146, "Missile Expansion"),
        PickupPlacementData(6, 147, "Missile Expansion"),
        PickupPlacementData(6, 148, "Missile Expansion"),
        PickupPlacementData(100, 149, "Energy Tank"),
        PickupPlacementData(6, 150, "Missile Expansion"),
        PickupPlacementData(6, 151, "Missile Expansion"),
        PickupPlacementData(6, 152, "Missile Expansion"),
        PickupPlacementData(6, 154, "Missile Expansion"),
    ]


# Converts a hexadecimal string to a base 10 integer.
def hexToInt(hexToConvert):
    return int(hexToConvert, 16)


# Converts an integer to a hexadecimal string.
def intToHex(intToConvert):
    return (hex(intToConvert)[2:]).upper()


# Converts a hexadecimal string to binary data.
def hexToData(hexToConvert):
    return bytes.fromhex(hexToConvert)


# Reverses the endianness of a hexadecimal string.
def reverseEndianness(hexToReverse):
    assert (len(hexToReverse) % 2) == 0
    hexPairs = []
    for i in range(len(hexToReverse) // 2):
        hexPairs.append(hexToReverse[2 * i] + hexToReverse[2 * i + 1])
    reversedHexPairs = hexPairs[::-1]
    outputString = ""
    for pair in reversedHexPairs:
        outputString += pair
    return outputString


# Pads a hexadecimal string with 0's until it meets the provided length.
def padHex(hexToPad, numHexCharacters):
    returnHex = hexToPad
    while len(returnHex) < numHexCharacters:
        returnHex = "0" + returnHex
    return returnHex


# Substitutes every incidence of a keyword in a string with a hex version of the passed number.
def replaceWithHex(originalString, keyword, number, numHexDigits=4):
    numHexString = reverseEndianness(padHex(intToHex(number), numHexDigits))
    return originalString.replace(keyword, numHexString)


# Generate a game with vanilla item placements
def genVanillaGame():
    pickupsList = []
    for itemIndex, itemName in zip(SuperMetroidConstants.itemIndexList, SuperMetroidConstants.vanillaPickupList):
        if itemName in SuperMetroidConstants.ammoItemList:
            pickupsList.append(
                PickupPlacementData(SuperMetroidConstants.defaultAmmoItemToQuantity[itemName], itemIndex, itemName)
            )
        else:
            pickupsList.append(PickupPlacementData(1, itemIndex, itemName))
    return pickupsList


# Adds the ability to start the game with items
# Takes a list of PickupPlacementData
# Irrelevent fields need not be specified.
def addStartingInventory(f, pickups, itemGetRoutineAddressesDict):
    if len(pickups) > 100:
        print(
            "ERROR: Unreasonable amount of starting items detected. Starting items will not be placed. Did you send correct information to the patcher?"
        )
        return
    f.seek(0x1C0000)
    f.write(len(pickups).to_bytes(2, "little"))
    for startingItem in pickups:
        itemName = startingItem.itemName
        if itemName in SuperMetroidConstants.ammoItemList:
            itemName += " " + str(startingItem.quantityGiven)
        routineAddress = itemGetRoutineAddressesDict[itemName] - 1
        f.write(routineAddress.to_bytes(2, "little"))

    awardStartingInventoryRoutine = (
        "AF0080B8AAE00000F020DAE220A99048C220A9FAFF48E220A98548C2208A0AAABF0080B8486BFACA80DB6B"
    )
    functionToReturnProperly = "A95FF6486B"
    awardStartingInventoryRoutineAddress = 0x08763A
    functionToReturnProperlyAddress = 0x02FFFB

    f.seek(awardStartingInventoryRoutineAddress)
    f.write(hexToData(awardStartingInventoryRoutine))
    f.seek(functionToReturnProperlyAddress)
    f.write(hexToData(functionToReturnProperly))


# This is just a python function that applies a modified version of
# Kazuto's More_Efficient_PLM_Items.asm patch without an assembler.
# Please, send lots of thanks to Kazuto for this, I could not have done
# Any of this without their hard work.
def writeKazutoMoreEfficientItemsHack(f, itemTypesList):
    # Where we start writing our data in the actual file.
    # Inclusive - first byte written here.
    inFileInitialOffset = 0x026099

    # Where the game believes data to be at runtime.
    # Equivalent to InFileInitialOffset in placement.
    # Influences addressing.
    # Excludes the bank address, which is implicitly 84
    inMemoryInitialOffset = 0xE099

    # Where we start writing PLM Headers for items.
    inMemoryPLMHeaderOffset = 0xEED7
    inFilePLMHeaderOffset = 0x026ED7

    # Each item represents two bytes in each table
    itemGetTableSize = len(itemTypesList) * 2
    itemGFXTableSize = itemGetTableSize

    # Calculate addresses of some important things.
    VRAMItemNormalAddr = inMemoryInitialOffset + 0x04
    VRAMItemBallAddr = VRAMItemNormalAddr + 0x0C
    startAddr = VRAMItemBallAddr + 0x10
    GFXAddr = startAddr + 0x0B
    gotoAddr = GFXAddr + 0x08
    VRAMItemBlockAddr = gotoAddr + 0x08
    respawnAddr = VRAMItemBlockAddr + 0x08
    blockLoopAddr = respawnAddr + 0x04
    GFXAddrB = blockLoopAddr + 0x13
    blockGotoAddr = GFXAddrB + 0x10
    getItemAddr = blockGotoAddr + 0x04
    tablePtrAddr = getItemAddr + 0x05

    # ASM Functions
    tableLoadFuncAddr = tablePtrAddr + 0x04
    lavaRiseFuncAddr = tableLoadFuncAddr + 0x1D

    # Tables
    itemGetTableAddr = lavaRiseFuncAddr + 0x07
    itemGFXTableAddr = itemGetTableAddr + itemGetTableSize

    # Item Data
    itemPLMDataAddr = itemGFXTableAddr + itemGFXTableSize

    # Write Data
    # Setup
    # Don't bother reading this, it's a 1 for 1 recreation of the Setup portion of Kazuto's asm file.
    # Or at least it should be.
    f.seek(inFileInitialOffset)
    f.write(tableLoadFuncAddr.to_bytes(2, "little") + itemGFXTableAddr.to_bytes(2, "little"))
    # VRAMItem_Normal
    f.write(
        bytearray([0x7C, 0x88, 0xA9, 0xDF, 0x2E, 0x8A])
        + inMemoryInitialOffset.to_bytes(2, "little")
        + bytearray([0x24, 0x87])
        + startAddr.to_bytes(2, "little")
    )
    # VRAMItem_Ball
    f.write(
        bytearray([0x7C, 0x88, 0xA9, 0xDF, 0x2E, 0x8A])
        + inMemoryInitialOffset.to_bytes(2, "little")
        + bytearray([0x2E, 0x8A, 0xAF, 0xDF, 0x2E, 0x8A, 0xC7, 0xDF])
    )
    # Start
    f.write(
        bytearray([0x24, 0x8A]) + gotoAddr.to_bytes(2, "little") + bytearray([0xC1, 0x86, 0x89, 0xDF, 0x4E, 0x87, 0x16])
    )
    # .Gfx (1)
    f.write(bytearray([0x4F, 0xE0, 0x67, 0xE0, 0x24, 0x87]) + GFXAddr.to_bytes(2, "little"))
    # Goto
    f.write(bytearray([0x24, 0x8A, 0xA9, 0xDF, 0x24, 0x87]) + getItemAddr.to_bytes(2, "little"))
    # VRAMItem_Block
    f.write(
        bytearray([0x2E, 0x8A])
        + inMemoryInitialOffset.to_bytes(2, "little")
        + bytearray([0x24, 0x87])
        + blockLoopAddr.to_bytes(2, "little")
    )
    # Respawn
    f.write(bytearray([0x2E, 0x8A, 0x32, 0xE0]))
    # BlockLoop
    f.write(
        bytearray([0x2E, 0x8A, 0x07, 0xE0, 0x7C, 0x88])
        + respawnAddr.to_bytes(2, "little")
        + bytearray([0x24, 0x8A])
        + blockGotoAddr.to_bytes(2, "little")
        + bytearray([0xC1, 0x86, 0x89, 0xDF, 0x4E, 0x87, 0x16])
    )
    # .Gfx (2)
    f.write(
        bytearray([0x4F, 0xE0, 0x67, 0xE0, 0x3F, 0x87])
        + GFXAddrB.to_bytes(2, "little")
        + bytearray([0x2E, 0x8A, 0x20, 0xE0, 0x24, 0x87])
        + blockLoopAddr.to_bytes(2, "little")
    )
    # BlockGoto
    f.write(bytearray([0x24, 0x8A]) + respawnAddr.to_bytes(2, "little"))
    # GetItem
    f.write(bytearray([0x99, 0x88, 0xDD, 0x8B, 0x02]))
    f.write(tableLoadFuncAddr.to_bytes(2, "little") + itemGetTableAddr.to_bytes(2, "little"))

    # ASM Functions
    # LoadItemTable
    f.write(hexToData("B900008512BF371C7EC92BEF9005E9540080F638E9D7EE4AA8B112A860"))
    # LavaRise
    f.write(bytearray([0xA9, 0xE0, 0xFF, 0x8D, 0x7C, 0x19, 0x60]))

    # Item Tables
    # Initial item table hexstrings.
    itemTableBytes = []
    GFXTableBytes = []

    # Size of the data pointed to for each entry.
    itemGetLength = 0x07
    itemGFXLength = 0x0E
    itemTotalLength = itemGetLength + itemGFXLength

    # Pointers to next item PLM data
    itemNextGetData = itemPLMDataAddr
    itemNextGFXData = itemPLMDataAddr + itemGetLength

    # Get table bytes one item at a time.
    for itemType in itemTypesList:
        # Add bytes to tables
        itemTableBytes.append(itemNextGetData.to_bytes(2, "little"))
        GFXTableBytes.append(itemNextGFXData.to_bytes(2, "little"))
        # Increment Data Pointers
        itemNextGetData = itemNextGetData + itemTotalLength
        itemNextGFXData = itemNextGFXData + itemTotalLength

    # Write tables to file
    for itemTableBytePair in itemTableBytes:
        f.write(itemTableBytePair)
    for GFXTableBytePair in GFXTableBytes:
        f.write(GFXTableBytePair)

    # Item PLM Data
    # This acquire data should do nothing but display a message box.
    # The actual "effects" of picking up the item are determined in
    # Messagebox display routines instead, as items for this player
    # Are the same PLM as an item that is for another player in the
    # Session. We already check which player it's for there and I
    # Honestly can't for the life of me decode how PLMs actually work,
    # So that's just where it happens. It is quite nice since this also
    # Works for the player receiving items from others, as the only thing
    # That actually happens is that a Messagebox appears for the player (i.e.
    # There is no actual item entity in the game world being picked up).
    genericAcquireData = bytearray([0xF3, 0x88, 0x00, 0x00, 0x13, 0x3A, 0x8A])
    for itemType in itemTypesList:
        # Construct the item's graphics data.
        currentItemGFXData = [0x64, 0x87]
        currentItemGFXData += itemType.GFXOffset.to_bytes(2, "big")
        for paletteByte in itemType.paletteBytes:
            currentItemGFXData.append(paletteByte)
        currentItemGFXData += [0x3A, 0x8A]
        try:
            assert len(currentItemGFXData) == itemGFXLength
        except:
            print(
                f"ERROR: Invalid-size graphics data supplied for item type {itemType.itemName}:\n {currentItemGFXData} should be only 14(0x0E) bytes, is instead {str(len(currentItemGFXData))}."
            )
            return
        # Write to file
        f.write(genericAcquireData)
        f.write(bytearray(currentItemGFXData))

    # Now we write out the PLM Header Data
    f.seek(inFilePLMHeaderOffset)
    normalItemHex = bytearray([0x64, 0xEE]) + VRAMItemNormalAddr.to_bytes(2, "little")
    ballItemHex = bytearray([0x64, 0xEE]) + VRAMItemBallAddr.to_bytes(2, "little")
    blockItemHex = bytearray([0x8E, 0xEE]) + VRAMItemBlockAddr.to_bytes(2, "little")
    for itemType in itemTypesList:
        f.write(normalItemHex)
    for itemType in itemTypesList:
        f.write(ballItemHex)
    for itemType in itemTypesList:
        f.write(blockItemHex)
    # Write native item graphics that aren't already in the ROM
    # This is primarily for what were originally CRE items like Missile Expansions.
    f.seek(0x049100)
    # FIXME - REMOVE DEPENDENCE ON CURRENT WORKING DIRECTORY!

    with VRAM_ITEMS_PATH.open("rb") as f2:
        f.write(f2.read())
    return inMemoryPLMHeaderOffset


# Places the items into the game.
def placeItems(f, filePath, itemGetRoutineAddressesDict, pickupDataList, playerName=None):
    # Initialize MessageBoxGenerator
    messageBoxGenerator = MessageBoxGenerator(f)

    # Necessary for applying the Kazuto More Efficient Items Patch
    itemTypes = {}
    # Locations of item sprites
    # Stored little-endian
    nativeItemSpriteLocations = {
        "Energy Tank": 0x0091,
        "Missile Expansion": 0x0092,
        "Super Missile Expansion": 0x0093,
        "Power Bomb Expansion": 0x0094,
        "Morph Ball Bombs": 0x0080,
        "Charge Beam": 0x008B,
        "Ice Beam": 0x008C,
        "Hi-Jump Boots": 0x0084,
        "Speed Booster": 0x008A,
        "Wave Beam": 0x008D,
        "Spazer Beam": 0x008F,
        "Spring Ball": 0x0082,
        "Varia Suit": 0x0083,
        "Gravity Suit": 0x0081,
        "X-Ray Scope": 0x0089,
        "Plasma Beam": 0x008E,
        "Grapple Beam": 0x0088,
        "Space Jump": 0x0086,
        "Screw Attack": 0x0085,
        "Morph Ball": 0x0087,
        "Reserve Tank": 0x0090,
    }

    # None indicates default palette
    # Item Palettes for native sprites
    # None is eqv. to all 0's.
    nativeItemPalettes = {
        "Energy Tank": None,
        "Missile Expansion": None,
        "Super Missile Expansion": None,
        "Power Bomb Expansion": None,
        "Morph Ball Bombs": None,
        "Charge Beam": None,
        "Ice Beam": bytearray([0x00, 0x03, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00]),
        "Hi-Jump Boots": None,
        "Speed Booster": None,
        "Wave Beam": bytearray([0x00, 0x02, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00]),
        "Spazer Beam": None,
        "Spring Ball": None,
        "Varia Suit": None,
        "Gravity Suit": None,
        "X-Ray Scope": bytearray([0x01, 0x01, 0x00, 0x00, 0x03, 0x03, 0x00, 0x00]),
        "Plasma Beam": bytearray([0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00]),
        "Grapple Beam": None,
        "Space Jump": None,
        "Screw Attack": None,
        "Morph Ball": None,
        "Reserve Tank": None,
    }

    # TODO: Add a placeholder-type sprite to available native graphics sprites
    # REMINDER: After doing so increment the initial GFXDataLocation address
    nextPickupGFXDataLocation = "0095"
    itemGfxAdded = {}
    for pickup in pickupDataList:
        if not pickup.itemName in itemTypes:
            if pickup.nativeGraphics:
                if pickup.nativeSpriteName == "Default":
                    itemTypes[pickup.itemName] = ItemType(
                        pickup.itemName, nativeItemSpriteLocations[pickup.itemName], nativeItemPalettes[pickup.itemName]
                    )
                else:
                    itemTypes[pickup.itemName] = ItemType(
                        pickup.itemName,
                        nativeItemSpriteLocations[pickup.nativeSpriteName],
                        nativeItemPalettes[pickup.nativeSpriteName],
                    )
            else:
                # TODO: Patch pickup graphics into ROM from file
                # TODO: Add message box generation
                itemGfxAdded[pickup.itemName] = pickup.graphicsFileName
                nextPickupGFXDataLocation = padHex(intToHex(hexToInt(nextPickupGFXDataLocation) + 1), 4)
                pass

    # FOR MULTIWORLD
    # Add items which don't exist in the base game.
    # EDIT: This commented code is very old and likely incompatible with current methods.

    # Generate list of items which do not exist in the base game.
    # WIP
    # nextPLMId = "EF2B"
    # for item in itemsInOrderList:
    # if not(item in itemPLMIDs):
    # itemPLMIDs[item] = nextPLMId

    # itemMessageIDs[item] = itemMessageIDs["Wave Beam"]
    # itemMessageWidths[item] = "Small"

    # itemMessageAddresses = None #TODO - Create these dynamically.

    # itemTypes.append(ItemType(item, ))
    # nextPLMId = intToHex(hexToInt(nextPLMId) + 4)

    itemTypeList = itemTypes.values()
    plmHeaderOffset = writeKazutoMoreEfficientItemsHack(f, itemTypeList)
    # Generate dict of item PLMIDs. Since there's no more guarantee of ordering here, we create this
    # at patch time.
    itemPLMIDs = {}

    for itemType in itemTypeList:
        itemPLMIDs[itemType.itemName] = plmHeaderOffset
        plmHeaderOffset += 4
    itemPLMIDs["No Item"] = 0xB62F

    # How much an increment for each slot above increases the value of the PLM ID.
    # We will calculate this on the fly depending on how many new items are added to this ROM.
    # TODO: Rewrite this based on len(itemTypes)
    itemPLMBlockTypeMultiplier = 0x54

    # Patch ROM.
    # This part of the code is ugly as sin, I apologize.
    spoilerPath = filePath[: filePath.rfind(".")] + "_SPOILER.txt"
    print("Spoiler file generating at " + spoilerPath + "...")
    spoilerFile = open(spoilerPath, "w")
    print(type(SuperMetroidConstants.itemIndexList))
    for i, item in enumerate(pickupDataList):
        patcherIndex = SuperMetroidConstants.itemIndexList.index(item.pickupIndex)
        print(
            f"pickupIndex: {item.pickupIndex}, patcherIndex: {patcherIndex}, location: {SuperMetroidConstants.locationNamesList[patcherIndex]}"
        )
        # Write PLM Data.
        f.seek(SuperMetroidConstants.itemPLMLocationList[patcherIndex])
        # If there is no item in this location, we should NOT try to calculate a PLM-type offset,
        # As this could give us an incorrect PLM ID.
        if item.itemName == "No Item":
            f.write(itemPLMIDs[item.itemName].to_bytes(2, "little"))
            continue
        f.write(
            (
                itemPLMIDs[item.itemName]
                + itemPLMBlockTypeMultiplier * SuperMetroidConstants.itemPLMBlockTypeList[patcherIndex]
            ).to_bytes(2, "little")
        )
        # Write Message Box Data.
        # ITEM TABLE FORMAT
        # 2 PAGES PER TABLE
        # TABLE 1: MESSAGEBOX HEADER LOCATION
        # TABLE 2: MESSAGEBOX CONTENT LOCATION
        # TABLE 3: MESSAGEBOX SIZE
        # TABLE 4: MESSAGEBOX ID. USED TO CALCULATE IMPORTANT VALUES.
        # TABLE 5: ITEM COLLECTION ROUTINE. REWARDS ITEMS TO PLAYER ON PICKUP.
        # This table is not present in the vanilla ROM, and is used with the custom routines.
        # See documentation on memory alterations at the top of this document.

        # Each table entry is two bytes wide, hence the doubling.
        memoryBaseLocation = 0x029A00 + SuperMetroidConstants.itemLocationList[patcherIndex] * 2

        f.seek(memoryBaseLocation)
        # TODO: Handle width and height separately.
        if item.itemName in SuperMetroidConstants.itemMessageNonstandardSizes:
            f.write((0x0080).to_bytes(2, "big"))
            f.seek(memoryBaseLocation + 0x400)
            f.write(SuperMetroidConstants.itemMessageNonstandardSizes[item.itemName].to_bytes(2, "little"))
        else:
            f.write((0x4080).to_bytes(2, "big"))
            f.seek(memoryBaseLocation + 0x400)
            f.write((0x4000).to_bytes(2, "big"))

        f.seek(memoryBaseLocation + 0x200)
        f.write(SuperMetroidConstants.itemMessageAddresses[item.itemName].to_bytes(2, "little"))

        f.seek(memoryBaseLocation + 0x600)
        f.write(SuperMetroidConstants.itemMessageIDs[item.itemName].to_bytes(2, "little"))

        f.seek(memoryBaseLocation + 0x800)
        # If item is meant for a different player, it will do nothing at all.
        # This is not the same as there not being an item in this position -
        # The item will be there, it will just have no effect for the SM player.
        if playerName is not None and not item.ownerName == playerName:
            f.write(itemGetRoutineAddressesDict["No Item"].to_bytes(2, "little"))
        else:
            effectiveItemName = item.itemName
            if item.itemName in SuperMetroidConstants.ammoItemList:
                effectiveItemName = f"{item.itemName} {item.quantityGiven}"
            f.write(itemGetRoutineAddressesDict[effectiveItemName].to_bytes(2, "little"))

        # Write spoiler log
        spoilerFile.write(f"{SuperMetroidConstants.locationNamesList[patcherIndex]}: {item.itemName}\n")
    spoilerFile.close()


def patchROM(ROMFilePath, itemList=None, playerName=None, recipientList=None, **kwargs):
    # Open ROM File
    f = open(ROMFilePath, "r+b", buffering=0)
    # Open Patcher Data Output File
    patcherOutputPath = ROMFilePath[: ROMFilePath.rfind(".")] + "_PatcherData.json"
    patcherOutput = open(patcherOutputPath, "w")
    patcherOutputJson = {"patcherData": []}
    # Generate item placement if none has been provided.
    # This will give a warning message, as this is only appropriate for debugging patcher features.
    if itemList is None:
        itemList = genVanillaGame()
        startingItems = None
        print("Item list was not supplied to ROM patcher. Generating Vanilla placement with no starting items.")
    else:
        try:
            assert len(itemList) == 100
        except:
            print("ERROR: Non-Empty item list didn't meet length requirement. Aborting ROM Patch.")
            return

    # Now write our new routines to memory.
    # First we append new routines to free space
    # At the end of bank 85.
    baseRoutineWritingAddress = 0x029643

    # Routines stored as hexadecimal.
    #
    # We handle writing these in the program itself instead of as static patches,
    # Because I write them myself and don't want to manually recalculate addresses
    # Each time I test changes.
    #
    # Keyphrases starting in - will be substituted with addresses.
    # These must be of appropriate length or size calculations might fail.
    # onPickupFoundRoutine = -alp
    # getMessageHeaderDataRoutine  = -bta
    # getMessageHeaderRoutine = -gma
    # getMessageContentRoutine = -dlt
    onPickupFoundRoutine = "8D1F1CC91C00F00AC914009006C91900B00160AF74FF7FC90100D01CAF7CFF7F8D1F1CA500DA48AF7EFF7F850068A20000FC0000FA8500605ADAA22000BF6ED87E9FCEFF7FCACAE00000D0F1A22000A00000BFCEFF7F38FFAEFF7FC90000F0028004EAEA801A8F8EFF7FA90100CF8EFF7FF008C90080080A288003C88002D0EDCACAE00000D0CBC00100F043AF52097EAAA9DE00E00000F00A18695C06CAE00000D0F6AAA02000BF000070DA5AFA7A9FAEFF7FDA5AFA7ACACA8888C00000D0E7A22000A900009F8EFF7FCACAE00000D0F5A22000BFCEFF7F38FFAEFF7F9F8EFF7FCACAE00000D0ECA0F000A22000BF8EFF7FC90000D00A9838E91000A8CACA80EDBFCEFF7F9FAEFF7FBF8EFF7FC90100F004C84A80F7A900009F8EFF7F980A8F8EFF7FAABD00A08D1F1CFC00A2FA7A60"
    getMessageHeaderDataRoutine = "20-gmaA920008516B900009F00327EC8C8E8E8C616D0F160"
    getMessageHeaderRoutine = (
        "AD1F1CC91C00F00AC914009009C91900B004A0408060AF74FF7FC90100D006AF76FF7FA860DAAF8EFF7FAABF009A85A8FA60"
    )
    getMessageContentRoutine = "AD1F1CC91C00F00AC91400902AC91900B025AD1F1C3A0A85340A186534AABD9F868500BDA58638E50085094A8516A50918698000850960AF74FF7FC90100D016AF78FF7FA88400AF7AFF7F4A85160A18698000850960DAAF8EFF7FAABF009C85A88400BF009E854A85160A186980008509FA60"
    # KEY NOTE: WRITE ROUTINE ADDRESSES LITTLE ENDIAN!!!
    routines = [onPickupFoundRoutine, getMessageHeaderDataRoutine, getMessageHeaderRoutine, getMessageContentRoutine]
    routineAddresses = []
    routineAddressRefs = ["-alp", "-bta", "-gma", "-dlt"]
    currentAddress = baseRoutineWritingAddress
    inGameAddress = 0x9643
    f.seek(currentAddress)
    # Calculate routine addresses
    for i in range(len(routines)):
        routineAddresses.append(inGameAddress)
        inGameAddress += len(routines[i]) // 2
        currentAddress += len(routines[i]) // 2

    # Replace subroutine references with their addresses and write them to the ROM file.
    for i in range(len(routines)):
        for j in range(len(routines)):
            routines[i] = replaceWithHex(routines[i], routineAddressRefs[j], routineAddresses[j])
        f.write(hexToData(routines[i]))

    # Flags have their endianness reversed before being written.
    itemGetRoutinesDict = {}
    # Not all routines here are written to ROM,
    # Only those which we determine are used in game.
    # This is why passing items from multiworld session that this player receives is necessary.
    # availableItemGetRoutinesDict = {}

    beamBitFlagsDict = {
        "Charge Beam": 0x1000,
        "Ice Beam": 0x0002,
        "Wave Beam": 0x0001,
        "Spazer Beam": 0x0004,
        "Plasma Beam": 0x0008,
    }

    equipmentBitFlagsDict = {
        "Varia Suit": 0x0001,
        "Spring Ball": 0x0002,
        "Morph Ball": 0x0004,
        "Screw Attack": 0x0008,
        "Hi-Jump Boots": 0x0100,
        "Space Jump": 0x0200,
        "Speed Booster": 0x2000,
        "Morph Ball Bombs": 0x1000,
        "Gravity Suit": 0x0020,
    }

    ammoGetTemplates = {
        "Energy Tank": "ADC4091869-qty8DC4098DC20960",
        "Reserve Tank": "ADD4091869-qty8DD409ADC009D003EEC00960",
        "Missile Expansion": "ADC8091869-qty8DC809ADC6091869-qty8DC60922CF998060",
        "Super Missile Expansion": "ADCC091869-qty8DCC09ADCA091869-qty8DCA09220E9A8060",
        "Power Bomb Expansion": "ADD0091869-qty8DD009ADCE091869-qty8DCE09221E9A8060",
    }

    # For new ammo-type items.
    customAmmoGetTemplates = {}

    # Make all the get routines and templates.
    grappleGet = "ADA2090900408DA209ADA4090900408DA409222E9A8060"
    xRayGet = "ADA2090900808DA209ADA4090900808DA409223E9A8060"
    equipmentGetTemplate = "ADA20909-eqp8DA209ADA40909-eqp8DA40960"
    beamGetTemplate = "A9-eqp0DA8098DA809A9-eqp0DA6098DA609A9-eqp0A2908001CA609A9-eqp4A2904001CA609228DAC9060"

    # Note that if items appear more than once with different implementations, things will break horribly.
    # If you want major items with different effects, give them a new name -
    # Ex. Instead of "Spazer" and "Plasma" for a progressive spazer hack, call it
    # "Progressive Spazer"
    # Will still try its damnedest if you give it conflicting info, but can't give multiple effects to an item that it thinks is the same.
    # This is why ammo item names have the quantity appended to them - since having differing quantities makes them effectively different items.
    equipmentGets = {}
    equipmentGets["X-Ray Scope"] = bytes.fromhex(xRayGet)
    equipmentGets["Grapple Beam"] = bytes.fromhex(grappleGet)
    for itemName, bitFlags in equipmentBitFlagsDict.items():
        equipmentHex = replaceWithHex(equipmentGetTemplate, "-eqp", bitFlags)
        equipmentGets[itemName] = bytes.fromhex(equipmentHex)
    for itemName, bitFlags in beamBitFlagsDict.items():
        equipmentHex = replaceWithHex(beamGetTemplate, "-eqp", bitFlags)
        equipmentGets[itemName] = bytes.fromhex(equipmentHex)

    # Create individual routines from ASM templates.
    # Note that the exact effect is hardcoded in, so ex. wave beam and ice beam are two different routines.
    # This is because I'm lazy and we absolutely have room for it.
    allItemsList = itemList.copy()
    if "startingItems" in kwargs:
        allItemsList += kwargs["startingItems"]
    for pickup in allItemsList:
        if pickup.ownerName is None or pickup.ownerName == playerName:
            if pickup.pickupItemEffect == "Default":
                if pickup.itemName in SuperMetroidConstants.ammoItemList:
                    effectivePickupName = f"{pickup.itemName} {pickup.quantityGiven}"
                    if not effectivePickupName in itemGetRoutinesDict:
                        print(effectivePickupName)
                        pickupHex = replaceWithHex(ammoGetTemplates[pickup.itemName], "-qty", pickup.quantityGiven)
                        itemGetRoutinesDict[effectivePickupName] = bytes.fromhex(pickupHex)
                elif pickup.itemName in SuperMetroidConstants.toggleItemList:
                    if not pickup.itemName in itemGetRoutinesDict:
                        itemGetRoutinesDict[pickup.itemName] = equipmentGets[pickup.itemName]
                else:
                    print(
                        'ERROR: Cannot specify itemPickupEffect as "Default" for an item which does not exist in the vanilla game.'
                    )
            else:
                if pickup.itemName in SuperMetroidConstants.ammoItemList:
                    effectivePickupName = f"{pickup.itemName} {pickup.quantityGiven}"
                    if not effectivePickupName in itemGetRoutinesDict:
                        pickupHex = replaceWithHex(
                            customAmmoGetTemplates[pickup.pickupItemEffect], "-qty", pickup.quantityGiven
                        )
                        itemGetRoutinesDict[effectivePickupName] = bytes.fromhex(pickupHex)
                elif pickup.itemName in SuperMetroidConstants.toggleItemList:
                    # Overwrite vanilla behavior for this item if vanilla.
                    # Otherwise add new item effect for the item type.
                    # Note that adding multiple toggle items with the same name and different effects has undefined behavior.
                    if not pickup.itemName in itemGetRoutinesDict:
                        if pickup.pickupItemEffect in equipmentGets:
                            itemGetRoutinesDict[pickup.itemName] = equipmentGets[pickup.pickupItemEffect]
                    # Otherwise add new effect
                else:
                    print("ERROR: Custom item pickup behaviors are not yet implemented.")

    # This is a command that will do nothing, used for items that are meant to go to other players.
    # 60 is hex for the RTS instruction. In other words when called it will immediately return.
    itemGetRoutinesDict["No Item"] = (0x60).to_bytes(1, "little")

    # Write them to memory and store their addresses in a dict.
    # This is critical, as we will use these addresses to store to a table that dictates
    # What an item will do when picked up.
    # We'll be appending them to the same place as messagebox code, so we'll keep the
    # Address and file pointer we had from before.
    # We may want to move these somewhere else later.
    itemGetRoutineAddressesDict = {}
    # Use this to make sure the item data tables, which contain data about pickups, isn't overwritten.
    passedTables = False
    for itemName, routine in itemGetRoutinesDict.items():
        # Don't overwrite the tables
        if (inGameAddress + len(routine) // 2) >= 0x9A00 and not passedTables:
            f.seek(0x2A400)
            inGameAddress = 0xA400
            passedTables = True
        # KEY CHANGE HERE - BIG NOT LITTLE ENDIAN STORED HERE!
        itemGetRoutineAddressesDict[itemName] = inGameAddress
        f.write(routine)
        inGameAddress += len(routine)
        currentAddress += len(routine)

    # Output item routine info to a json file for use in the interface
    itemRoutinesJsonOutput = []
    for (itemName, routineAddress) in itemGetRoutineAddressesDict.items():
        itemRoutinesJsonOutput.append(
            {"itemName": itemName, "routineAddress": reverseEndianness(padHex(intToHex(routineAddress), 4))}
        )
        print(itemName + " has routine address " + reverseEndianness(padHex(intToHex(routineAddress), 4)))
    patcherOutputJson["patcherData"].append({"itemRoutines": itemRoutinesJsonOutput})

    # Patch Item Placements into the ROM.
    placeItems(f, ROMFilePath, itemGetRoutineAddressesDict, itemList)

    # Add starting items patch
    if "startingItems" in kwargs:
        addStartingInventory(f, kwargs["startingItems"], itemGetRoutineAddressesDict)
    else:
        f.seek(0x1C0000)
        f.write((0).to_bytes(2, "little"))

    # Modify/overwrite existing routines.
    overwriteRoutines = []
    overwriteRoutineAddresses = []

    # Modify Message Box Routines To Allow Customizable Behavior
    overwriteJSRToPickupRoutine = "20-alp"
    overwriteGetMessageHeaderRoutine = "20-gmaA20000B900009F00327EE8E8C8C8E04000D0F0A0000020B88220-bta60"
    overwriteJSRToGetMessageRoutine = "20-dltEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEA"
    overwriteJSRToGetHeaderRoutine = "205A82"
    overwriteCrateriaWakeupRoutine = "AF73D87E290400F007BD0000AA4CE6E5E8E860"

    # Addresses to write routines to in Headerless ROM file.
    overwriteJSRToPickupRoutineAddress = "028086"
    overwriteGetMessageHeaderRoutineAddress = "02825A"
    overwriteJSRToGetMessageRoutineAddress = "0282E5"
    overwriteJSRToGetHeaderRoutineAddress = "028250"
    overwriteCrateriaWakeupRoutineAddress = "07E652"

    # Skip intro cutscene and/or Space Station Ceres depending on parameters passed to function.
    # Default behavior is to skip straight to landing site.
    introOptionChoice = "Skip Intro And Ceres"
    if "introOptionChoice" in kwargs:
        introOptionChoice = kwargs["introOptionChoice"]
    # Check to make sure intro option choice doesn't conflict with custom start point.
    if "customSaveStart" in kwargs:
        if introOptionChoice != "Skip Intro And Ceres":
            print("ERROR: Cannot set custom start without also skipping Intro and Ceres.")
    if introOptionChoice != "Vanilla":
        if introOptionChoice == "Skip Intro":
            # TODO: Convert this to static patch.
            introRoutine = "9CE20DADDA09D01B223AF690A906008D9F079C8B07ADEA098F08D87E22008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"

            introRoutineAddress = "016EB4"

            overwriteRoutines.extend([introRoutine])
            overwriteRoutineAddresses.extend([introRoutineAddress])
        elif introOptionChoice == "Skip Intro And Ceres":
            introRoutine = "9CE20DADDA09D01E223AF690A9-rgn8D9F07A9-sav8D8B07ADEA098F08D87EAD520922008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"
            introRoutineAddress = "016EB4"
            # Custom save start should be a list/tuple with two values:
            # Region name and save station index
            # This is subject to change
            # TODO: Support Ceres
            if "customSaveStart" in kwargs:
                customStart = kwargs["customSaveStart"]
                regionHex = SuperMetroidConstants.regionToHexDict[customStart[0]]
                saveHex = reverseEndianness(padHex(intToHex(customStart[1]), 4))
                introRoutine = introRoutine.replace("-rgn", regionHex)
                introRoutine = introRoutine.replace("-sav", saveHex)
            else:
                introRoutine = introRoutine.replace("-rgn", "0000")
                introRoutine = introRoutine.replace("-sav", "0000")
        else:
            print("WARNING: Invalid option entered for introOptionChoice. Defaulting to vanilla intro behavior...")

        overwriteRoutines.extend([introRoutine])
        overwriteRoutineAddresses.extend([introRoutineAddress])

    overwriteRoutines.extend(
        [
            overwriteJSRToPickupRoutine,
            overwriteGetMessageHeaderRoutine,
            overwriteJSRToGetMessageRoutine,
            overwriteJSRToGetHeaderRoutine,
            overwriteCrateriaWakeupRoutine,
        ]
    )
    overwriteRoutineAddresses.extend(
        [
            overwriteJSRToPickupRoutineAddress,
            overwriteGetMessageHeaderRoutineAddress,
            overwriteJSRToGetMessageRoutineAddress,
            overwriteJSRToGetHeaderRoutineAddress,
            overwriteCrateriaWakeupRoutineAddress,
        ]
    )

    # Apply static patches.
    # Many of these patches are provided by community members -
    # See top of document for details.
    # Dictionary of files associated with static patch names:
    staticPatchDict = {"InstantG4": "g4_skip.ips", "MaxAmmoDisplay": "max_ammo_display.ips"}
    patches_dir = Path(__file__).parent.joinpath("Patches")

    if "staticPatches" in kwargs:
        staticPatches = kwargs["staticPatches"]
        for patch in staticPatches:
            if patch in staticPatchDict:
                IPSPatcher.applyIPSPatch(patches_dir.joinpath(staticPatchDict[patch]), ROMFilePath)
            else:
                print(f"Provided patch {patch} does not exist!")

    # Replace references with actual addresses.
    for i in range(len(overwriteRoutines)):
        for j in range(len(routines)):
            overwriteRoutines[i] = replaceWithHex(overwriteRoutines[i], routineAddressRefs[j], routineAddresses[j])

    # Write to file
    for i, routine in enumerate(overwriteRoutines):
        currentAddress = hexToInt(overwriteRoutineAddresses[i])
        f.seek(currentAddress)
        f.write(hexToData(routine))

    # MULTIWORLD ROUTINES:
    # Appended to bank 90. Used to work the game's events in our favor.
    # TODO: Convert this to an ips patch?
    multiworldExecuteArbitraryFunctionRoutine = "E220A98348C220AF72FF7F486B"

    f.seek(0x087FF0)
    f.write(hexToData(multiworldExecuteArbitraryFunctionRoutine))

    # Routines to append to bank $83.

    multiworldItemGetRoutine = "AD1F1C22808085A900008F74FF7FAF80FF7F8D420A6B"
    multiworldRoutineAddressStart = 0x01AD66

    multiworldRoutines = [multiworldItemGetRoutine]

    f.seek(multiworldRoutineAddressStart)
    for routine in multiworldRoutines:
        f.write(hexToData(routine))

    json.dump(patcherOutputJson, patcherOutput, indent=4, sort_keys=True)
    patcherOutput.close()
    f.close()
    print("ROM modified successfully.")


if __name__ == "__main__":
    # Build in this to make it faster to test.
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
    patchesToApply = ["InstantG4", "MaxAmmoDisplay"]
    patchROM(
        filePath,
        rawRandomizedExampleItemPickupData(),
        startingItems=[PickupPlacementData(1, -1, "Morph Ball")],
        introOptionChoice="Skip Intro And Ceres",
        staticPatches=patchesToApply,
    )
    # patchROM(filePath, None, startingItems = ["Morph Ball", "Reserve Tank", "Energy Tank"], introOptionChoice = "Skip Intro And Ceres", customSaveStart = ["Brinstar", 0])
