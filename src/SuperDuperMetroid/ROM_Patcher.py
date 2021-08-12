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

import random
import json
import sys
import os
from hexhelper import HexHelper
from SM_Constants import SuperMetroidConstants

class MessageBoxGenerator:
    # List of characters that messages are allowed to have.
    # Note that messages will be converted to uppercase
    # Before removing invalid characters.
    allowedCharacterList = ['0', '1', '2', '3', '4', '5',
                            '6', '7', '8', '9', 'A', 'B',
                            'C', 'D', 'E', 'F', 'G', 'H',
                            'I', 'J', 'K', 'L', 'M', 'N',
                            'O', 'P', 'Q', 'R', 'S', 'T',
                            'U', 'V', 'W', 'X', 'Y', 'Z',
                            '%', ' ', '&', '-', '.', ',',
                            '\'', '?', '!']

    # First digit of tuple is row in tilemap, second is column.
    # The messagebox character tilemap is 16x16.
    characterToTilemapPosDict = {
        '1'  : ( 0,  0),
        '2'  : ( 0,  1),
        '3'  : ( 0,  2),
        '4'  : ( 0,  3),
        '5'  : ( 0,  4),
        '6'  : ( 0,  5),
        '7'  : ( 0,  6),
        '8'  : ( 0,  7),
        '9'  : ( 0,  8),
        '0'  : ( 0,  9),
        '%'  : ( 0, 10),
        ' '  : ( 4, 14),
        '&'  : (12,  8),
        '-'  : (12, 15),
        'A'  : (14,  0),
        'B'  : (14,  1),
        'C'  : (14,  2),
        'D'  : (14,  3),
        'E'  : (14,  4),
        'F'  : (14,  5),
        'G'  : (14,  6),
        'H'  : (14,  7),
        'I'  : (14,  8),
        'J'  : (14,  9),
        'K'  : (14, 10),
        'L'  : (14, 11),
        'M'  : (14, 12),
        'N'  : (14, 13),
        'O'  : (14, 14),
        'P'  : (14, 15),
        'Q'  : (15,  0),
        'R'  : (15,  1),
        'S'  : (15,  2),
        'T'  : (15,  3),
        'U'  : (15,  4),
        'V'  : (15,  5),
        'W'  : (15,  6),
        'X'  : (15,  7),
        'Y'  : (15,  8),
        'Z'  : (15,  9),
        '.'  : (15, 10),
        ','  : (15, 11),
        '\'' : (15, 12),
        '?'  : (15, 14),
        '!'  : (15, 15)
    }

    maxMessageLengths = {
        "Small" : 19,
        "Large" : 26
    }

    # Maximum length in characters of a standard message box.
    # Technically some, like the missile pickup, are bigger, but we're ignoring those.
    messageBoxMaxLength = 19


    # Create the message box generator.
    # TODO: Place initial method *after* appended messagebox routines.
    def __init__(self, ROMFile, initialAddress = "029643"):
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
        if (len(messageText) > len(strippedMessage)):
            print("Warning Message box text " + messageText + " contains unsupported characters. These will be stripped from the message.\nMessage boxes support the latin alphabet (will be converted to uppercase only), the arabic numerals 0-9, spaces, and a limited set of miscellaneous characters: ?!,.'&-%")
        messageText = strippedMessage

        # If the message is too long, cut it off.
        # We'll also include a warning if this happens.
        if (len(messageText) > maxMessageLengths(messageBoxSize)):
            print(f"Warning: Message box text {messageText} exceeds maximum length of message box. Message will be cut to first 19 characters.")
            messageText = messageText[:maxMessageLengths(messageBoxSize)]
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
            print(f"Warning: You are attempting to create a message with size paramater {messageBoxSize}, which is not a supported size.\nSupported sizes are Small and Large")
            return

        # Record our addition of this message.
        if messageBoxSize == "Small":
            if messageText in smallMessagePointerTable.keys():
                print(f"Warning: The message {messageText} has already been added to this ROM.\nPlease consult the current maintainer of this patcher.")
            else:
                self.smallMessagePointerTable[messageText] = messageText
        elif messageBoxSize == "Large":
            if messageText in largeMessagePointerTable.keys():
                print(f"Warning: The message {messageText} has already been added to this ROM.\nPlease consult the current maintainer of this patcher.")
            else:
                self.largeMessagePointerTable[messageText] = messageText

        # Write hex to ROM
        self.file.seek(int(self.currentAddress, 16))
        self.file.write(bytes.fromhex(format(messageHex, 'x')))

        # Update address for next message box write.
        self.currentAddress = (hex(int(self.currentAddress, 16) + 64)[2:]).upper()
        # Prepend a 0 to make it look more presentable.
        # Not important, I'm just a perfectionist.
        if len(self.currentAddress) == 5:
            self.currentAddress = "0" + self.currentAddress

class ItemType:
    itemName  = None
    GFXOffset = None
    # Most items use this all 00's palette, so just have it as the defaultl.
    paletteBytes = ["00", "00", "00", "00", "00", "00", "00", "00"]
    def __init__(self, itemName, GFXOffset, paletteBytes = None):
        self.itemName  = itemName
        self.GFXOffset = GFXOffset
        if paletteBytes is not None:
            self.paletteBytes = paletteBytes

# Class which represents items being passed to the game from the generator
# TODO: Implement this more fully
class PickupPlacementData:
    def __init__(self, quantityGiven, pickupIndex, itemName, pickupItemEffect = "Default", nativeGraphics = True, ownerName = None, graphicsFileName = None, nativeSpriteName = "Default"):
        self.quantityGiven    = quantityGiven
        self.pickupIndex      = pickupIndex
        self.itemName         = itemName
        self.pickupItemEffect = pickupItemEffect
        self.nativeGraphics   = nativeGraphics
        self.ownerName        = ownerName
        self.graphicsFileName = graphicsFileName
        self.nativeSpriteName = nativeSpriteName

# Generate a game with vanilla item placements
def genVanillaGame():
    pickupsList = []
    for itemIndex, itemName in zip(SuperMetroidConstants.itemIndexList, SuperMetroidConstants.vanillaPickupList):
        if itemName in SuperMetroidConstants.ammoItemList:
            pickupsList.append(PickupPlacementData(SuperMetroidConstants.defaultAmmoItemToQuantity[itemName], itemIndex, itemName))
        else:
            pickupsList.append(PickupPlacementData(1, itemIndex, itemName))
    return pickupsList

# This is just a python function that applies a modified version of
# Kazuto's More_Efficient_PLM_Items.asm patch without an assembler.
# Please, send lots of thanks to Kazuto for this, I could not have done
# Any of this without their hard work.
def writeKazutoMoreEfficientItemsHack(f, itemTypesList):
    # Where we start writing our data in the actual file.
    # Inclusive - first byte written here.
    inFileInitialOffset     = "026099"

    # Where the game believes data to be at runtime.
    # Equivalent to InFileInitialOffset in placement.
    # Influences addressing.
    # Excludes the bank address, which is implicitly 84
    inMemoryInitialOffset   = "E099"

    # Where we start writing PLM Headers for items.
    inFilePLMHeaderOffset   = "EED7"
    inMemoryPLMHeaderOffset = "026ED7"

    # Each item represents two bytes in each table
    itemGetTableSize = HexHelper.intToHex(len(itemTypesList) * 2)
    itemGFXTableSize = itemGetTableSize

    # Calculate addresses of some important things.
    # Format:
    # Next Address     |                                                       |Offset of prior data |                     |Prior Data Size |

    # Setup
    VRAMItemNormalAddr = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(inMemoryInitialOffset) + HexHelper.hexToInt("04"            )), 4)
    VRAMItemBallAddr   = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(VRAMItemNormalAddr   ) + HexHelper.hexToInt("0C"            )), 4)
    startAddr          = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(VRAMItemBallAddr     ) + HexHelper.hexToInt("10"            )), 4)
    GFXAddr            = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(startAddr            ) + HexHelper.hexToInt("0B"            )), 4)
    gotoAddr           = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(GFXAddr              ) + HexHelper.hexToInt("08"            )), 4)
    VRAMItemBlockAddr  = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(gotoAddr             ) + HexHelper.hexToInt("08"            )), 4)
    respawnAddr        = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(VRAMItemBlockAddr    ) + HexHelper.hexToInt("08"            )), 4)
    blockLoopAddr      = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(respawnAddr          ) + HexHelper.hexToInt("04"            )), 4)
    GFXAddrB           = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(blockLoopAddr        ) + HexHelper.hexToInt("13"            )), 4)
    blockGotoAddr      = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(GFXAddrB             ) + HexHelper.hexToInt("10"            )), 4)
    getItemAddr        = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(blockGotoAddr        ) + HexHelper.hexToInt("04"            )), 4)
    tablePtrAddr       = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(getItemAddr          ) + HexHelper.hexToInt("05"            )), 4)

    # ASM Functions
    tableLoadFuncAddr  = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(tablePtrAddr         ) + HexHelper.hexToInt("04"            )), 4)
    lavaRiseFuncAddr   = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(tableLoadFuncAddr    ) + HexHelper.hexToInt("1D"            )), 4)

    # Tables
    itemGetTableAddr   = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(lavaRiseFuncAddr     ) + HexHelper.hexToInt("07"            )), 4)
    itemGFXTableAddr   = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(itemGetTableAddr     ) + HexHelper.hexToInt(itemGetTableSize)), 4)

    # Item Data
    itemPLMDataAddr    = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(itemGFXTableAddr     ) + HexHelper.hexToInt(itemGFXTableSize)), 4)

    # Write Data
    # Setup
    # Don't bother reading this, it's a 1 for 1 recreation of the Setup portion of Kazuto's asm file.
    # Or at least it should be.
    f.seek(HexHelper.hexToInt(inFileInitialOffset))
    f.write(HexHelper.hexToData(HexHelper.reverseEndianness(tableLoadFuncAddr) + HexHelper.reverseEndianness(itemGFXTableAddr)))
    # VRAMItem_Normal
    f.write(HexHelper.hexToData("7C88A9DF2E8A"                                 + HexHelper.reverseEndianness(inMemoryInitialOffset) + "2487"         + HexHelper.reverseEndianness(startAddr)))
    # VRAMItem_Ball
    f.write(HexHelper.hexToData("7C88A9DF2E8A"                                 + HexHelper.reverseEndianness(inMemoryInitialOffset) + "2E8AAFDF2E8AC7DF"))
    # Start
    f.write(HexHelper.hexToData("248A"                                         + HexHelper.reverseEndianness(gotoAddr)              + "C18689DF4E8716"))
    # .Gfx (1)
    f.write(HexHelper.hexToData("4FE067E02487"                                 + HexHelper.reverseEndianness(GFXAddr)))
    # Goto
    f.write(HexHelper.hexToData("248AA9DF2487"                                 + HexHelper.reverseEndianness(getItemAddr)))
    # VRAMItem_Block
    f.write(HexHelper.hexToData("2E8A"                                         + HexHelper.reverseEndianness(inMemoryInitialOffset) + "2487"         + HexHelper.reverseEndianness(blockLoopAddr)))
    # Respawn
    f.write(HexHelper.hexToData("2E8A32E0"))
    # BlockLoop
    f.write(HexHelper.hexToData("2E8A07E07C88"                                 + HexHelper.reverseEndianness(respawnAddr)           + "248A"         + HexHelper.reverseEndianness(blockGotoAddr) + "C18689DF4E8716"))
    # .Gfx (2)
    f.write(HexHelper.hexToData("4FE067E03F87"                                 + HexHelper.reverseEndianness(GFXAddrB)              + "2E8A20E02487" + HexHelper.reverseEndianness(blockLoopAddr)))
    # BlockGoto
    f.write(HexHelper.hexToData("248A"                                         + HexHelper.reverseEndianness(respawnAddr)))
    # GetItem
    f.write(HexHelper.hexToData("9988DD8B02"))
    f.write(HexHelper.hexToData(HexHelper.reverseEndianness(tableLoadFuncAddr) + HexHelper.reverseEndianness(itemGetTableAddr)))

    # ASM Functions
    # LoadItemTable
    f.write(HexHelper.hexToData("B900008512BF371C7EC92BEF9005E9540080F638E9D7EE4AA8B112A860"))
    # LavaRise
    f.write(HexHelper.hexToData("A9E0FF8D7C1960"))

    # Item Tables
    # Initial item table hexstrings.
    itemTableBytes  = ""
    GFXTableBytes   = ""

    # Size of the data pointed to for each entry.
    itemGetLength   = "07"
    itemGFXLength   = "0E"
    itemTotalLength = HexHelper.intToHex(HexHelper.hexToInt(itemGetLength) + HexHelper.hexToInt(itemGFXLength))

    # Pointers to next item PLM data
    itemNextGetData = itemPLMDataAddr
    itemNextGFXData = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(itemPLMDataAddr) + HexHelper.hexToInt(itemGetLength)), 4)

    # Get table bytes one item at a time.
    for itemType in itemTypesList:
        # Add bytes to tables
        itemTableBytes += HexHelper.reverseEndianness(itemNextGetData)
        GFXTableBytes  += HexHelper.reverseEndianness(itemNextGFXData)
        # Increment Data Pointers
        itemNextGetData = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(itemNextGetData) + HexHelper.hexToInt(itemTotalLength)), 4)
        itemNextGFXData = HexHelper.padHex(HexHelper.intToHex(HexHelper.hexToInt(itemNextGFXData) + HexHelper.hexToInt(itemTotalLength)), 4)

    # Write tables to file
    f.write(HexHelper.hexToData(itemTableBytes))
    f.write(HexHelper.hexToData(GFXTableBytes ))

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
    genericAcquireData = "F3880000133A8A"
    for itemType in itemTypesList:
        # Construct the item's graphics data.
        currentItemGFXData  = "6487"
        currentItemGFXData += itemType.GFXOffset
        for paletteByte in itemType.paletteBytes:
            currentItemGFXData += paletteByte
        currentItemGFXData += "3A8A"
        try:
            assert (len(currentItemGFXData) // 2) == HexHelper.hexToInt(itemGFXLength)
        except:
            errorMsg  = f"ERROR: Invalid-size graphics data supplied for item type {itemType.itemName}:\n {currentItemGFXData} should be only 14(0x0E) bytes, is instead {str(len(currentItemGFXData))}(0x{HexHelper.padHex(HexHelper.intToHex(len(currentItemGFXData)), 2)})."
            print(errorMsg)
            return
        # Write to file
        f.write(HexHelper.hexToData(genericAcquireData))
        f.write(HexHelper.hexToData(currentItemGFXData))

    # Now we write out the PLM Header Data
    f.seek(HexHelper.hexToInt(inMemoryPLMHeaderOffset))
    normalItemHex = "64EE" + HexHelper.reverseEndianness(VRAMItemNormalAddr)
    ballItemHex   = "64EE" + HexHelper.reverseEndianness(VRAMItemBallAddr)
    blockItemHex  = "8EEE" + HexHelper.reverseEndianness(VRAMItemBlockAddr)
    for itemType in itemTypesList:
        f.write(HexHelper.hexToData(normalItemHex))
    for itemType in itemTypesList:
        f.write(HexHelper.hexToData(ballItemHex))
    for itemType in itemTypesList:
        f.write(HexHelper.hexToData(blockItemHex))
    # Write native item graphics that aren't already in the ROM
    # This is primarily for what were originally CRE items like Missile Expansions.
    f.seek(HexHelper.hexToInt("049100"))
    with open("C:\\Users\\Dood\\Dropbox\\SM Modding\\Publish\\VramItems.bin", "rb") as f2:
        f.write(f2.read())
    return inFilePLMHeaderOffset


# Places the items into the game.
def placeItems(f, filePath, itemGetRoutineAddressesDict, pickupDataList, playerName = None):
    # Initialize MessageBoxGenerator
    messageBoxGenerator = MessageBoxGenerator(f)

    # Necessary for applying the Kazuto More Efficient Items Patch
    itemTypes = {}
    # Locations of item sprites
    # Stored little-endian
    nativeItemSpriteLocations = {
        "Energy Tank"             : "0091",
        "Missile Expansion"       : "0092",
        "Super Missile Expansion" : "0093",
        "Power Bomb Expansion"    : "0094",
        "Morph Ball Bombs"        : "0080",
        "Charge Beam"             : "008B",
        "Ice Beam"                : "008C",
        "Hi-Jump Boots"           : "0084",
        "Speed Booster"           : "008A",
        "Wave Beam"               : "008D",
        "Spazer Beam"             : "008F",
        "Spring Ball"             : "0082",
        "Varia Suit"              : "0083",
        "Gravity Suit"            : "0081",
        "X-Ray Scope"             : "0089",
        "Plasma Beam"             : "008E",
        "Grapple Beam"            : "0088",
        "Space Jump"              : "0086",
        "Screw Attack"            : "0085",
        "Morph Ball"              : "0087",
        "Reserve Tank"            : "0090"
    }

    # None indicates default palette
    # Item Palettes for native sprites
    # None is eqv. to all 0's.
    nativeItemPalettes = {
        "Energy Tank"             : None,
        "Missile Expansion"       : None,
        "Super Missile Expansion" : None,
        "Power Bomb Expansion"    : None,
        "Morph Ball Bombs"        : None,
        "Charge Beam"             : None,
        "Ice Beam"                : ["00", "03", "00", "00", "00", "03", "00", "00"],
        "Hi-Jump Boots"           : None,
        "Speed Booster"           : None,
        "Wave Beam"               : ["00", "02", "00", "00", "00", "02", "00", "00"],
        "Spazer Beam"             : None,
        "Spring Ball"             : None,
        "Varia Suit"              : None,
        "Gravity Suit"            : None,
        "X-Ray Scope"             : ["01", "01", "00", "00", "03", "03", "00", "00"],
        "Plasma Beam"             : ["00", "01", "00", "00", "00", "01", "00", "00"],
        "Grapple Beam"            : None,
        "Space Jump"              : None,
        "Screw Attack"            : None,
        "Morph Ball"              : None,
        "Reserve Tank"            : None
    }

    # TODO: Add a placeholder-type sprite to available native graphics sprites
    # REMINDER: After doing so increment the initial GFXDataLocation address
    nextPickupGFXDataLocation = "0095"
    itemGfxAdded = {}
    for pickup in pickupDataList:
        if not pickup.itemName in itemTypes:
            if pickup.nativeGraphics:
                if pickup.nativeSpriteName == "Default":
                    itemTypes[pickup.itemName] = ItemType(pickup.itemName, nativeItemSpriteLocations[pickup.itemName], nativeItemPalettes[pickup.itemName])
                else:
                    itemTypes[pickup.itemName] = ItemType(pickup.itemName, nativeItemSpriteLocations[pickup.nativeSpriteName], nativeItemPalettes[pickup.nativeSpriteName])
            else:
                #TODO: Patch pickup graphics into ROM from file
                #TODO: Add message box generation
                itemGfxAdded[pickup.itemName] = pickup.graphicsFileName
                nextPickupGFXDataLocation = HexHelper.padHex(HexHelper.intToHex(hexHelper.hexToInt(nextPickupGFXDataLocation) + 1), 4)
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
            # nextPLMId = HexHelper.intToHex(HexHelper.hexToInt(nextPLMId) + 4)


    itemTypeList = itemTypes.values()
    plmHeaderOffset = writeKazutoMoreEfficientItemsHack(f, itemTypeList)
    # Generate dict of item PLMIDs. Since there's no more guarantee of ordering here, we create this
    # at patch time.
    itemPLMIDs = {}

    for itemType in itemTypeList:
        itemPLMIDs[itemType.itemName] = plmHeaderOffset
        plmHeaderOffset = HexHelper.intToHex(HexHelper.hexToInt(plmHeaderOffset) + 4)
    itemPLMIDs["No Item"] = "B62F"

    # How much an increment for each slot above increases the value of the PLM ID.
    # We will calculate this on the fly depending on how many new items are added to this ROM.
    # TODO: Rewrite this based on len(itemTypes)
    itemPLMBlockTypeMultiplier = hex((int("54", 16) + 0 * 4))[2:].upper()

    # Patch ROM.
    # This part of the code is ugly as sin, I apologize.
    spoilerPath = filePath[:filePath.rfind(".")] + "_SPOILER.txt"
    print("Spoiler file generating at " + spoilerPath + "...")
    spoilerFile = open(spoilerPath, 'w')
    for i, item in enumerate(pickupDataList):
        patcherIndex = SuperMetroidConstants.itemIndexList.index(item.pickupIndex)
        # Write PLM Data.
        f.seek(HexHelper.hexToInt(SuperMetroidConstants.itemPLMLocationList[patcherIndex]))
        # If there is no item in this location, we should NOT try to calculate a PLM-type offset,
        # As this could give us an incorrect PLM ID.
        if (item.itemName == "No Item"):
            PLMID = HexHelper.hexToInt(itemPLMIDs[item.itemName])
            PLMHexadecimalID = bytes.fromhex(format(PLMID, 'x'))[::-1]
            f.write(PLMHexadecimalID)
            continue
        PLMID = HexHelper.hexToInt(itemPLMIDs[item.itemName]) + (HexHelper.hexToInt(itemPLMBlockTypeMultiplier) * SuperMetroidConstants.itemPLMBlockTypeList[patcherIndex])
        PLMHexadecimalID = bytes.fromhex(format(PLMID, 'x'))[::-1]
        f.write(PLMHexadecimalID)

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
        memoryBaseLocation = HexHelper.hexToInt("029A00") + (HexHelper.hexToInt(SuperMetroidConstants.itemLocationList[patcherIndex]) * 2)
        f.seek(memoryBaseLocation)
        # TODO: Handle width and height separately.
        if item.itemName in SuperMetroidConstants.itemMessageNonstandardSizes:
            f.write(bytes.fromhex("8000")[::-1])
            f.seek(memoryBaseLocation + HexHelper.hexToInt("400"))
            f.write(bytes.fromhex(SuperMetroidConstants.itemMessageNonstandardSizes[item.itemName])[::-1])
        else:
            f.write(bytes.fromhex("8040")[::-1])
            f.seek(memoryBaseLocation + HexHelper.hexToInt("400"))
            f.write(bytes.fromhex("0040")[::-1])

        f.seek(memoryBaseLocation + HexHelper.hexToInt("200"))
        f.write(bytes.fromhex(SuperMetroidConstants.itemMessageAddresses[item.itemName])[::-1])

        f.seek(memoryBaseLocation + HexHelper.hexToInt("600"))
        f.write(bytes.fromhex(SuperMetroidConstants.itemMessageIDs[item.itemName])[::-1])

        f.seek(memoryBaseLocation + HexHelper.hexToInt("800"))
        # If item is meant for a different player, it will do nothing at all.
        # This is not the same as there not being an item in this position -
        # The item will be there, it will just have no effect for the SM player.
        if playerName is not None and not item.ownerName == playerName:
            f.write(HexHelper.hexToData(itemGetRoutineAddressesDict["No Item"]))
        else:
            effectiveItemName = item.itemName
            if item.itemName in SuperMetroidConstants.ammoItemList:
                effectiveItemName = f"{item.itemName} {item.quantityGiven}"
            f.write(HexHelper.hexToData(itemGetRoutineAddressesDict[effectiveItemName]))


        # Write spoiler log
        spoilerFile.write(f"{SuperMetroidConstants.locationNamesList[patcherIndex]}: {item.itemName}\n")
    spoilerFile.close()

def patchROM(ROMFilePath, itemList = None, playerName = None, recipientList = None, **kwargs):
    # Open ROM File
    f = open(ROMFilePath, 'r+b', buffering = 0)
    # Open Patcher Data Output File
    patcherOutputPath = filePath[:filePath.rfind(".")] + "_PatcherData.json"
    patcherOutput = open(patcherOutputPath, 'w')
    patcherOutputJson = {"patcherData" : []}
    # Generate item placement if none has been provided.
    # This will give a warning message, as this is only appropriate for debugging patcher features.
    if itemList is None:
        # FIXME
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
    baseRoutineWritingAddress = "029643"

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
    onPickupFoundRoutine = "8D1F1CC91C00F00AC914009006C91900B00160AF74FF7FC90100D01CAF7CFF7F8D1F1CA500DA48AF7EFF7F850068A20000FC0000FA8500605ADAA22000BF6ED87E9FCEFF7FCACAE00000D0F1AFD0FF7F38EFB0FF7FC90000F0278F8EFF7FA90100CF8EFF7FF01AC90080080A28D0F2A22000A90000EA9FAEFF7FCACAE00000D0F1A22000BFCEFF7F38FFAEFF7F9F8EFF7FCACAE00000D0ECA0F000A22000BF8EFF7FC90000D00A9838E91000A8CACA80EDBFCEFF7F9FAEFF7FBF8EFF7FC90100F004C84A80F7980A8F8EFF7FAABD00A08D1F1CFC00A2FA7A60"
    getMessageHeaderDataRoutine  = "20-gmaA920008516B900009F00327EC8C8E8E8C616D0F160"
    getMessageHeaderRoutine = "AD1F1CC91C00F00AC914009009C91900B004A0408060AF74FF7FC90100D006AF76FF7FA860DAAF8EFF7FAABF009A85A8FA60"
    getMessageContentRoutine = "AD1F1CC91C00F00AC91400902AC91900B025AD1F1C3A0A85340A186534AABD9F868500BDA58638E50085094A8516A50918698000850960AF74FF7FC90100D016AF78FF7FA88400AF7AFF7F4A85160A18698000850960DAAF8EFF7FAABF009C85A88400BF009E854A85160A186980008509FA60"

    routines = [onPickupFoundRoutine, getMessageHeaderDataRoutine, getMessageHeaderRoutine, getMessageContentRoutine]
    routineAddresses = []
    routineAddressRefs = ["-alp", "-bta", "-gma", "-dlt"]
    currentAddress = HexHelper.hexToInt(baseRoutineWritingAddress)
    inGameAddress = "9643"
    f.seek(currentAddress)
    # Calculate routine addresses
    for i in range(len(routines)):
        routineAddresses.append(HexHelper.reverseEndianness(inGameAddress))
        inGameAddress   = HexHelper.intToHex(HexHelper.hexToInt(inGameAddress) + (len(routines[i]) // 2))
        currentAddress += int(len(routines[i]) // 2)

    # Replace subroutine references with their addresses and write them to the ROM file.
    for i in range(len(routines)):
        for j in range(len(routines)):
            routines[i] = (routines[i]).replace(routineAddressRefs[j], routineAddresses[j])
        f.write(HexHelper.hexToData(routines[i]))

    # Flags have their endianness reversed before being written.
    itemGetRoutinesDict = {}
    # I hate this code
    # This is just all possible get routines, excluding filled ammo templates, of which only those deemed necessary are included.
    # Not all routines here are written to ROM
    # availableItemGetRoutinesDict = {}

    beamBitFlagsDict       = {
        "Charge Beam" : "1000",
        "Ice Beam"    : "0002",
        "Wave Beam"   : "0001",
        "Spazer Beam" : "0004",
        "Plasma Beam" : "0008"
    }

    equipmentBitFlagsDict = {
        "Varia Suit"       : "0001",
        "Spring Ball"      : "0002",
        "Morph Ball"       : "0004",
        "Screw Attack"     : "0008",
        "Hi-Jump Boots"    : "0100",
        "Space Jump"       : "0200",
        "Speed Booster"    : "2000",
        "Morph Ball Bombs" : "1000",
        "Gravity Suit"     : "0020"
    }

    ammoGetTemplates = {
        "Energy Tank"             : "ADC4091869-qty8DC4098DC20960",
        "Reserve Tank"            : "ADD4091869-qty8DD409ADC009D003EEC00960",
        "Missile Expansion"       : "ADC8091869-qty8DC809ADC6091869-qty8DC60922CF998060",
        "Super Missile Expansion" : "ADCC091869-qty8DCC09ADCA091869-qty8DCA09220E9A8060",
        "Power Bomb Expansion"    : "ADD0091869-qty8DD009ADCE091869-qty8DCE09221E9A8060"
    }

    # For new ammo-type items.
    customAmmoGetTemplates = {

    }

    # Make all the get routines and templates.
    grappleGet           = "ADA2090900408DA209ADA4090900408DA409222E9A8060"
    xRayGet              = "ADA2090900808DA209ADA4090900808DA409223E9A8060"
    equipmentGetTemplate = "ADA20909-eqp8DA209ADA40909-eqp8DA40960"
    beamGetTemplate      = "A9-eqp0DA8098DA809A9-eqp0DA6098DA609A9-eqp0A2908001CA609A9-eqp4A2904001CA609228DAC9060"

    # Note that if items appear more than once with different implementations, things will break horribly.
    # If you want major items with different effects, give them a new name -
    # Ex. Instead of "Spazer" and "Plasma" for a progressive spazer hack, call it
    # "Progressive Spazer"
    # Will still try its damnedest if you give it conflicting info, but can't give multiple effects to an item that it thinks is the same.
    # This is why ammo item names have the quantity appended to them - since having differing quantities makes them effectively different items.
    equipmentGets = {}
    equipmentGets["X-Ray Scope"]  = xRayGet
    equipmentGets["Grapple Beam"] = grappleGet
    for itemName, bitFlags  in equipmentBitFlagsDict.items():
        equipmentGets[itemName] = equipmentGetTemplate.replace("-eqp", HexHelper.reverseEndianness(bitFlags))
    for itemName, bitFlags in beamBitFlagsDict.items():
        equipmentGets[itemName] = beamGetTemplate.replace("-eqp", HexHelper.reverseEndianness(bitFlags))

    # Create individual routines from ASM templates.
    # Note that the exact effect is hardcoded in, so ex. wave beam and ice beam are two different routines.
    # This is because I'm lazy and we absolutely have room for it.
    for pickup in itemList:
        if pickup.ownerName is None or pickup.ownerName == playerName:

            if pickup.pickupItemEffect == "Default":
                if pickup.itemName in SuperMetroidConstants.ammoItemList:
                    if not f"{pickup.itemName} {pickup.quantityGiven}" in itemGetRoutinesDict:
                        print(f"{pickup.itemName} {pickup.quantityGiven}")
                        itemGetRoutinesDict[f"{pickup.itemName} {pickup.quantityGiven}"] = ammoGetTemplates[pickup.itemName].replace("-qty", HexHelper.reverseEndianness(HexHelper.padHex(HexHelper.intToHex(pickup.quantityGiven), 4)))
                elif pickup.itemName in SuperMetroidConstants.toggleItemList:
                    if not pickup.itemName in itemGetRoutinesDict:
                        itemGetRoutinesDict[pickup.itemName] = equipmentGets[pickup.itemName]
                else:
                    print("ERROR: Cannot specify itemPickupEffect as \"Default\" for an item which does not exist in the vanilla game.")
            else:
                if pickup.itemName in SuperMetroidConstants.ammoItemList:
                    if not f"{pickup.itemName} {pickup.quantityGiven}" in itemGetRoutinesDict:
                        itemGetRoutinesDict[f"{pickup.itemName} {pickup.quantityGiven}"] = customAmmoGetTemplates[pickup.pickupItemEffect].replace("-qty", HexHelper.reverseEndianness(HexHelper.padHex(HexHelper.intToHex(pickup.quantityGiven)), 4))
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
    itemGetRoutinesDict["No Item"] = "60"

    # Write them to memory and store their addresses in a dict.
    # This is critical, as we will use these addresses to store to a table that dictates
    # What an item will do when picked up.
    # We'll be appending them to the same place as messagebox code, so we'll keep the
    # Address and file pointer we had from before.
    # We may want to move these somewhere else later.
    itemGetRoutineAddressesDict = {}
    passedTables = False
    for itemName, routine in itemGetRoutinesDict.items():
        # Don't overwrite the tables
        if (HexHelper.hexToInt(inGameAddress) + int(len(routine) // 2)) >= HexHelper.hexToInt("9A00") and not passedTables:
            f.seek(HexHelper.hexToInt("2A400"))
            inGameAddress = "A400"
            passedTables = True
        itemGetRoutineAddressesDict[itemName] = HexHelper.reverseEndianness(inGameAddress)
        f.write(HexHelper.hexToData(routine))
        inGameAddress   = HexHelper.intToHex(HexHelper.hexToInt(inGameAddress) + (len(routine) // 2))
        currentAddress += int(len(routine) // 2)

    # Output item routine info to a json file for use in the interface
    itemRoutinesJsonOutput = []
    for (itemName, routineAddress) in itemGetRoutineAddressesDict.items():
        itemRoutinesJsonOutput.append({"itemName" : itemName, "routineAddress" : routineAddress})
        print(itemName + " has routine address " + routineAddress)
    patcherOutputJson["patcherData"].append({"itemRoutines" : itemRoutinesJsonOutput})

    # Patch Item Placements into the ROM.
    placeItems(f, ROMFilePath, itemGetRoutineAddressesDict, itemList)

    # Modify/overwrite existing routines.
    overwriteRoutines = []
    overwriteRoutineAddresses = []

    # Modify Message Box Routines To Allow Customizable Behavior
    overwriteJSRToPickupRoutine = "20-alp"
    overwriteGetMessageHeaderRoutine  = "20-gmaA20000B900009F00327EE8E8C8C8E04000D0F0A0000020B88220-bta60"
    overwriteJSRToGetMessageRoutine = "20-dltEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEA"
    overwriteJSRToGetHeaderRoutine = "205A82"

    # Addresses to write routines to in Headerless ROM file.
    overwriteJSRToPickupRoutineAddress = "028086"
    overwriteGetMessageHeaderRoutineAddress = "02825A"
    overwriteJSRToGetMessageRoutineAddress = "0282E5"
    overwriteJSRToGetHeaderRoutineAddress = "028250"

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
            introRoutine = "9CE20DADDA09D017A906008D9F079C8B07ADEA098F08D87E22008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"

            introRoutineAddress = "016EB4"

            overwriteRoutines.extend([introRoutine])
            overwriteRoutineAddresses.extend([introRoutineAddress])
        elif introOptionChoice == "Skip Intro And Ceres":
            introRoutine = "9CE20DADDA09D01AA9-rgn8D9F07A9-sav8D8B07ADEA098F08D87EAD520922008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"
            introRoutineAddress = "016EB4"
            # Custom save start should be a list/tuple with two values:
            # Region name and save station index
            # This is subject to change
            # TODO: Support Ceres
            if "customSaveStart" in kwargs:
                customStart = kwargs["customSaveStart"]
                regionHex = SuperMetroidConstants.regionToHexDict[customStart[0]]
                saveHex = HexHelper.reverseEndianness(HexHelper.padHex(HexHelper.intToHex(customStart[1]), 4))
                introRoutine = introRoutine.replace("-rgn", regionHex)
                introRoutine = introRoutine.replace("-sav", saveHex)
            else:
                introRoutine = introRoutine.replace("-rgn", "0000")
                introRoutine = introRoutine.replace("-sav", "0000")
        else:
            print("WARNING: Invalid option entered for introOptionChoice. Defaulting to vanilla intro behavior...")

        overwriteRoutines.extend([introRoutine])
        overwriteRoutineAddresses.extend([introRoutineAddress])


    overwriteRoutines.extend([overwriteJSRToPickupRoutine, overwriteGetMessageHeaderRoutine, overwriteJSRToGetMessageRoutine, overwriteJSRToGetHeaderRoutine])
    overwriteRoutineAddresses.extend([overwriteJSRToPickupRoutineAddress, overwriteGetMessageHeaderRoutineAddress, overwriteJSRToGetMessageRoutineAddress, overwriteJSRToGetHeaderRoutineAddress])

    # Apply static patches.
    # Many of these patches are provided by community members -
    # See top of document for details.
    # TODO

    # Replace references with actual addresses.
    for i in range(len(overwriteRoutines)):
        for j in range(len(routines)):
            overwriteRoutines[i] = (overwriteRoutines[i]).replace(routineAddressRefs[j], routineAddresses[j])

    # Write to file
    for i, routine in enumerate(overwriteRoutines):
        currentAddress = HexHelper.hexToInt(overwriteRoutineAddresses[i])
        f.seek(currentAddress)
        f.write(HexHelper.hexToData(routine))

    # MULTIWORLD ROUTINES:
    # Appended to bank 90. Used to work the game's events in our favor.
    # TODO: Convert this to an ips patch
    multiworldExecuteArbitraryFunctionRoutine = "E220A98348C220AF72FF7F486B"
    # Address relative to start of bank 90
    multiworldExecuteArbitraryFunctionRoutineAddress = "FFF0"

    if len(multiworldExecuteArbitraryFunctionRoutine) // 2 > 16:
        print("ERROR: Multiworld Function Redirect Function exceeds its maximum size.")

    f.seek(HexHelper.hexToInt("087FF0"))
    f.write(HexHelper.hexToData(multiworldExecuteArbitraryFunctionRoutine))

    # Routines to append to bank $83.


    multiworldItemGetRoutine = "AD1F1C22808085A900008F74FF7FAF80FF7F8D420A6B"
    multiworldRoutineAddressStart = "01AD66"

    multiworldRoutines = [multiworldItemGetRoutine]

    f.seek(HexHelper.hexToInt(multiworldRoutineAddressStart))
    for routine in multiworldRoutines:
        f.write(HexHelper.hexToData(routine))

    json.dump(patcherOutputJson, patcherOutput, indent=4, sort_keys=True)
    patcherOutput.close()
    f.close()
    print("ROM modified successfully.")

if __name__ == "__main__":
    # Build in this to make it faster to run.
    # Saves me some time.
    if os.path.isfile(os.getcwd() + "\\romfilepath.txt"):
        f = open(os.getcwd() + "\\romfilepath.txt", 'r')
        filePath = f.readline().rstrip()
        f.close()
    else:
        print("Enter full file path for your headerless Super Metroid ROM file.\nNote that the patcher DOES NOT COPY the game files - it will DIRECTLY OVERWRITE them. Make sure to create a backup before using this program.\nWARNING: Video game piracy is a crime - only use legally obtained copies of the game Super Metroid with this program.")
        filePath = input()
    patchROM(filePath, None, startingItems = ["Morph Ball", "Reserve Tank", "Energy Tank"], introOptionChoice = "Skip Intro And Ceres")
    #patchROM(filePath, None, startingItems = ["Morph Ball", "Reserve Tank", "Energy Tank"], introOptionChoice = "Skip Intro And Ceres", customSaveStart = ["Brinstar", 0])
