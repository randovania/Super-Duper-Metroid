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

# Useful for debugging.
def generateVanillaItemPlacement():
    vanillaItemList = [
        "Power Bomb Expansion",
        "Missile Expansion",
        "Missile Expansion",
        "Missile Expansion",
        "Missile Expansion",
        "Energy Tank",
        "Missile Expansion",
        "Morph Ball Bombs",
        
        "Energy Tank",
        "Missile Expansion",
        "Missile Expansion",
        "Super Missile Expansion",
        "Missile Expansion",
        "Power Bomb Expansion",
        "Super Missile Expansion",
        "Missile Expansion",
        
        "Super Missile Expansion",
        "Reserve Tank",
        "Missile Expansion",
        "Missile Expansion",
        "Missile Expansion",
        "Missile Expansion",
        "Charge Beam",
        
        "Power Bomb Expansion",
        "Missile Expansion",
        "Morph Ball",
        "Power Bomb Expansion",
        "Missile Expansion",
        "Energy Tank",
        "Energy Tank",
        "Super Missile Expansion",
        
        "Energy Tank",
        "Missile Expansion",
        "Energy Tank",
        "Missile Expansion",
        "Missile Expansion",
        "X-Ray Scope",
        "Power Bomb Expansion",
        
        "Power Bomb Expansion",
        "Missile Expansion",
        "Spazer Beam",
        "Energy Tank",
        "Missile Expansion",
        
        "Varia Suit",
        "Missile Expansion",
        "Ice Beam",
        "Missile Expansion",
        "Energy Tank",
        "Hi-Jump Boots",
        "Missile Expansion",
        "Missile Expansion",
        
        "Energy Tank",
        "Power Bomb Expansion",
        "Missile Expansion",
        "Missile Expansion",
        "Grapple Beam",
        "Reserve Tank",
        "Missile Expansion",
        "Missile Expansion",
        
        "Missile Expansion",
        "Missile Expansion",
        "Speed Booster",
        "Missile Expansion",
        "Wave Beam",
        "Missile Expansion",
        "Super Missile Expansion",
        
        "Missile Expansion",
        "Missile Expansion",
        "Power Bomb Expansion",
        "Power Bomb Expansion",
        "Missile Expansion",
        "Energy Tank",
        "Screw Attack",
        
        "Missile Expansion",
        
        "Missile Expansion",
        "Reserve Tank",
        "Missile Expansion",
        "Missile Expansion",
        "Energy Tank",
        "Super Missile Expansion",
        "Super Missile Expansion",
        "Gravity Suit",
        
        "Missile Expansion",
        "Super Missile Expansion",
        "Energy Tank",
        "Missile Expansion",
        "Super Missile Expansion",
        "Missile Expansion",
        "Missile Expansion",
        "Plasma Beam",
        
        "Missile Expansion",
        "Reserve Tank",
        "Missile Expansion",
        "Power Bomb Expansion",
        "Missile Expansion",
        "Super Missile Expansion",
        "Spring Ball",
        "Missile Expansion",
        
        "Energy Tank",
        "Space Jump"]
    return vanillaItemList
        
# Randomly places every item that would occur in the vanilla game.
# Almost never completable, purely for testing.
def generateLogiclessItemPlacement(startingItems = None):
    print("WARNING: Item list not sent to patcher. Generating logicless item placement.")
    # List each pickup in the game once for each time it appears.
    itemList = []
    itemList.extend(["Missile Expansion"] * 46)
    itemList.extend(["Super Missile Expansion"] * 10)
    itemList.extend(["Power Bomb Expansion"] * 10)
    itemList.extend(["Energy Tank"] * 14)
    itemList.extend(["Reserve Tank"] * 4)
    itemList.append("Spazer Beam")
    itemList.append("Charge Beam")
    itemList.append("Ice Beam")
    itemList.append("Plasma Beam")
    itemList.append("Wave Beam")
    itemList.append("Varia Suit")
    itemList.append("Gravity Suit")
    itemList.append("Morph Ball")
    itemList.append("Spring Ball")
    itemList.append("Morph Ball Bombs")
    itemList.append("Speed Booster")
    itemList.append("Grapple Beam")
    itemList.append("X-Ray Scope")
    itemList.append("Hi-Jump Boots")
    itemList.append("Space Jump")
    itemList.append("Screw Attack")
    # Remove items from placement to account for starting items.
    if startingItems != None:
        for item in startingItems:
            index = itemList.index(item)
            itemList[index] = "No Item"
    # Generate logicless item rando
    itemsInOrderList = []
    for i in range(100):
        item = random.choice(itemList)
        itemList.remove(item)
        itemsInOrderList.append(item)
    return itemsInOrderList

# TODO:
def getCustomSaveStationData(customSaveLocation):
    
    regionData = ""
    saveData   = ""
    return[regionData, saveData]

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
    # Next Address     |                  |Offset of prior data |           |Prior Data Size |
    
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
    # Write Graphics
    # TODO:
    f.seek(HexHelper.hexToInt("049100"))
    with open("C:\\Users\\Dood\\Dropbox\\SM Modding\\Publish\\VramItems.bin", "rb") as f2:
        f.write(f2.read())
    return
        

# Places the items into the game.
def placeItems(f, filePath, itemGetRoutineAddressesDict, itemsInOrderList, itemHoldersInOrderList = None, playerName = None):
    # Initialize MessageBoxGenerator
    messageBoxGenerator = MessageBoxGenerator(f)
    
    # Dictionary of nonstandard message box sizes
    # TODO: Replace this with something more elegant? Possibly.
    itemMessageNonstandardSizes = {
        "Missile Expansion"       : "0100",
        "Super Missile Expansion" : "0100",
        "Power Bomb Expansion"    : "0100",
        "Morph Ball Bombs"        : "0100",
        "Speed Booster"           : "0100",
        "Grapple Beam"            : "0100",
        "X-Ray Scope"             : "0100"}
    
    # Dictionary of item message locations
    itemMessageAddresses = {
        "Energy Tank"             : "877F",
        "Missile Expansion"       : "87BF",
        "Super Missile Expansion" : "88BF",
        "Power Bomb Expansion"    : "89BF",
        "Grapple Beam"            : "8ABF",
        "X-Ray Scope"             : "8BBF",
        "Varia Suit"              : "8CBF",
        "Spring Ball"             : "8CFF",
        "Morph Ball"              : "8D3F",
        "Screw Attack"            : "8D7F",
        "Hi-Jump Boots"           : "8DBF",
        "Space Jump"              : "8DFF",
        "Speed Booster"           : "8E3F",
        "Charge Beam"             : "8F3F",
        "Ice Beam"                : "8F7F",
        "Wave Beam"               : "8FBF",
        "Spazer Beam"             : "8FFF",
        "Plasma Beam"             : "903F",
        "Morph Ball Bombs"        : "907F",
        "Reserve Tank"            : "94FF",
        "Gravity Suit"            : "953F"}
    
    # The Message Box ID of all these vanilla items.
    itemMessageIDs = {
        "Energy Tank"             : "0001",
        "Missile Expansion"       : "0002",
        "Super Missile Expansion" : "0003",
        "Power Bomb Expansion"    : "0004",
        "Grapple Beam"            : "0005",
        "X-Ray Scope"             : "0006",
        "Varia Suit"              : "0007",
        "Spring Ball"             : "0008",
        "Morph Ball"              : "0009",
        "Screw Attack"            : "000A",
        "Hi-Jump Boots"           : "000B",
        "Space Jump"              : "000C",
        "Speed Booster"           : "000D",
        "Charge Beam"             : "000E",
        "Ice Beam"                : "000F",
        "Wave Beam"               : "0010",
        "Spazer Beam"             : "0011",
        "Plasma Beam"             : "0012",
        "Morph Ball Bombs"        : "0013",
        "Reserve Tank"            : "0019",
        "Gravity Suit"            : "001A"}
    
    # Widths for all messages, either "Small" or "Large".
    # Small boxes have a width of 19 tiles,
    # Large boxes have a width of 26 tiles.
    # This dictates how messages are generated.
    # If a message type is not in this dict,
    # It is "Small".
    # All non-item messages, such as save station menus, recharge stations, etc. are also always small.
    # This includes unused messages.
    # Note that messageboxes may have varying heights.
    itemMessageWidths = {
        "Energy Tank"             : "Small",
        "Missile Expansion"       : "Large",
        "Super Missile Expansion" : "Large",
        "Power Bomb Expansion"    : "Large",
        "Grapple Beam"            : "Large",
        "X-Ray Scope"             : "Large",
        "Varia Suit"              : "Small",
        "Spring Ball"             : "Small",
        "Morph Ball"              : "Small",
        "Screw Attack"            : "Small",
        "Hi-Jump Boots"           : "Small",
        "Space Jump"              : "Small",
        "Speed Booster"           : "Large",
        "Charge Beam"             : "Small",
        "Ice Beam"                : "Small",
        "Wave Beam"               : "Small",
        "Spazer Beam"             : "Small",
        "Plasma Beam"             : "Small",
        "Morph Ball Bombs"        : "Large",
        "Reserve Tank"            : "Small",
        "Gravity Suit"            : "Small"}
    
    # The 2-byte IDs of each of these pickups' PLMs.
    # Curiously, PLM order doesn't match item message order.
    itemPLMIDs = {
        "Energy Tank"             : "EED7",
        "Missile Expansion"       : "EEDB",
        "Super Missile Expansion" : "EEDF",
        "Power Bomb Expansion"    : "EEE3",
        "Morph Ball Bombs"        : "EEE7",
        "Charge Beam"             : "EEEB",
        "Ice Beam"                : "EEEF",
        "Hi-Jump Boots"           : "EEF3",
        "Speed Booster"           : "EEF7",
        "Wave Beam"               : "EEFB",
        "Spazer Beam"             : "EEFF",
        "Spring Ball"             : "EF03",
        "Varia Suit"              : "EF07",
        "Gravity Suit"            : "EF0B",
        "X-Ray Scope"             : "EF0F",
        "Plasma Beam"             : "EF13",
        "Grapple Beam"            : "EF17",
        "Space Jump"              : "EF1B",
        "Screw Attack"            : "EF1F",
        "Morph Ball"              : "EF23",
        "Reserve Tank"            : "EF27",
        # This will replace the item with nothing at all.
        # Its space will simply be empty, nothing will be there.
        # This is NOT the same as the "No Item" routine, which is
        # Attached to an actual item, but simply does nothing when picked up
        # To affect the player's current gamestate.
        "No Item"                 : "B62F"}
    
    # Necessary for applying the Kazuto More Efficient Items Patch
    itemTypes = [
        ItemType("Energy Tank"            , "0091"),
        ItemType("Missile Expansion"      , "0092"),
        ItemType("Super Missile Expansion", "0093"),
        ItemType("Power Bomb Expansion"   , "0094"),
        ItemType("Morph Ball Bombs"       , "0080"),
        ItemType("Charge Beam"            , "008B"),
        ItemType("Ice Beam"               , "008C" , ["00", "03", "00", "00", "00", "03", "00", "00"]),
        ItemType("Hi-Jump Boots"          , "0084"),
        ItemType("Speed Booster"          , "008A"),
        ItemType("Wave Beam"              , "008D" , ["00", "02", "00", "00", "00", "02", "00", "00"]),
        ItemType("Spazer Beam"            , "008F"),
        ItemType("Spring Ball"            , "0082"),
        ItemType("Varia Suit"             , "0083"),
        ItemType("Gravity Suit"           , "0081"),
        ItemType("X-Ray Scope"            , "0089" , ["01", "01", "00", "00", "03", "03", "00", "00"]),
        ItemType("Plasma Beam"            , "008E" , ["00", "01", "00", "00", "00", "01", "00", "00"]),
        ItemType("Grapple Beam"           , "0088"),
        ItemType("Space Jump"             , "0086"),
        ItemType("Screw Attack"           , "0085"),
        ItemType("Morph Ball"             , "0087"),
        ItemType("Reserve Tank"           , "0090"),
    ]
    
    # FOR MULTIWORLD
    # Add items which don't exist in the base game.
    
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
    
    # TODO: Include graphics for common, non VRAM items
    writeKazutoMoreEfficientItemsHack(f, itemTypes)
    
    # List of all possible item locations as they are ordered in memory.
    # This looks really good if you have a monospace font.
    # If you don't have one you're a chump.
    itemLocationList = [
        "00", "01", "02", "03", "04", "05", "06", "07",
        "08", "09", "0A", "0B", "0C", "0D", "0E", "0F",
        "10", "11", "12", "13",       "15", "16", "17",
        "18", "19", "1A", "1B", "1C", "1D", "1E", "1F",
              "21", "22", "23", "24", "25", "26", "27",
        "28", "29", "2A", "2B", "2C",
        "30", "31", "32", "33", "34", "35", "36", "37",
        "38", "39", "3A", "3B", "3C", "3D", "3E", "3F",
        "40", "41", "42", "43", "44",       "46", "47",
              "49", "4A", "4B", "4C", "4D", "4E", "4F",
        "50",

        "80", "81", "82", "83", "84", "85", "86", "87",
        "88", "89", "8A", "8B", "8C", "8D", "8E", "8F",
        "90", "91", "92", "93", "94", "95", "96", "97",
        "98",       "9A"]
    
    # List of item PLM type offsets.
    # Used to set items as shot block or chozo orbs when necessary,
    # Depending upon which location an item is placed into.
    itemPLMBlockTypeList = [
        0, 0, 2, 0, 0, 0, 0, 1,
        0, 0, 0, 0, 0, 1, 1, 0,
        0, 1, 2, 0,    0, 0, 1,
        0, 0, 0, 0, 0, 2, 0, 0,
           0, 1, 0, 0, 2, 1, 0,
        1, 0, 1, 2, 2,
        1, 2, 1, 2, 0, 1, 0, 0,
        0, 0, 0, 0, 1, 1, 2, 0,
        0, 2, 1, 0, 1,    0, 2,
           0, 0, 0, 0, 0, 2, 1,
        0,

        0, 1, 0, 0, 0, 0, 0, 1,
        0, 0, 0, 2, 0, 0, 0, 1,
        0, 1, 0, 0, 0, 0, 1, 2,
        0,       1]
    
    # How much an increment for each slot above increases the value of the PLM ID.
    # We will calculate this on the fly depending on how many new items are added to this ROM.
    # TODO: Rewrite this based on len(itemTypes)
    itemPLMBlockTypeMultiplier = hex((int("54", 16) + 0 * 4))[2:].upper()
    
    # List of item PLM Locations in ROM.
    # This is where we place each item's entity so that it will show up in the room.
    # Doing so overwrites the item that would have been there previously (i.e. in an unpatched ROM).
    itemPLMLocationList = [
        "781CC", "781E8", "781EE", "781F4", "78248", "78264", "783EE", "78404",
        "78432", "78464", "7846A", "78478", "78486", "784AC", "784E4", "78518",
        "7851E", "7852C", "78532", "78538",          "78608", "7860E", "78614",
        "7865E", "78676", "786DE", "7874C", "78798", "7879E", "787C2", "787D0",
                 "787FA", "78802", "78824", "78836", "7883C", "78876", "788CA",
        "7890E", "78914", "7896E", "7899C", "789EC",             
        "78ACA", "78AE4", "78B24", "78B46", "78BA4", "78BAC", "78BC0", "78BE6",
        "78BEC", "78C04", "78C14", "78C2A", "78C36", "78C3E", "78C44", "78C52",
        "78C66", "78C74", "78C82", "78CBC", "78CCA",          "78E6E", "78E74",
                 "78F30", "78FCA", "78FD2", "790C0", "79100", "79108", "79110",
        
        "79184",
        "7C265", "7C2E9", "7C2EF", "7C319", "7C337", "7C357", "7C365", "7C36D",
        "7C437", "7C43D", "7C47D", "7C483", "7C4AF", "7C4B5", "7C533", "7C559",
        "7C5DD", "7C5E3", "7C5EB", "7C5F1", "7C603", "7C609", "7C6E5", "7C74D",
        "7C755",          "7C7A7"]
    
    # List of location names for use in spoiler log.
    # Order is the same as prior 3 item lists.
    locationNamesList = [
        "Crateria Landing Site Power Bombs",
        "Crateria Ocean Underwater Missiles",
        "Crateria Ocean Cliff Missiles",
        "Crateria Ocean Morph Maze Missiles",
        "Crateria Moat Missiles",
        "Crateria Gauntlet Energy Tank",
        "Crateria Mother Brain Missiles",
        "Crateria Morph Ball Bombs",
        
        "Crateria Terminator Energy Tank",
        "Crateria Gauntlet Right Missiles",
        "Crateria Gauntlet Left Missiles",
        "Crateria Shinespark Shaft Super Missiles",
        "Crateria Final Missiles",
        "Green Brinstar Etecoons Power Bombs",
        "Pink Brinstar Spore Spawn Super Missiles",
        "Green Brinstar Early Supers Crumble Bridge Missiles",
        
        "Green Brinstar Early Supers Super Missiles",
        "Green Brinstar Reserve Tank",
        "Green Brinstar Reserve Tank Missiles 2",
        "Green Brinstar Reserve Tank Missiles",
        "Pink Brinstar Big Pink Grapple Missiles",
        "Pink Brinstar Big Pink Bottom Missiles",
        "Pink Brinstar Charge Beam",
        
        "Pink Brinstar Big Pink Grapple Power Bombs",
        "Green Brinstar Green Hill Zone Missiles",
        "Blue Brinstar Morph Ball",
        "Blue Brinstar Power Bombs",
        "Blue Brinstar Energy Tank Room Missiles",
        "Blue Brinstar Energy Tank",
        "Green Brinstar Etecoons Energy Tank",
        "Green Brinstar Etecoons Super Missiles",
        
        "Pink Brinstar Waterway Energy Tank",
        "Blue Brinstar First Missiles",
        "Pink Brinstar Wavegate Energy Tank",
        "Blue Brinstar Billy Mayes Missiles",
        "Blue Brinstar Billy Mayes' Double Offer Missiles",
        "Red Brinstar X-Ray Scope",
        "Red Brinstar Samus Eater Power Bombs",
        
        "Red Brinstar Alpha Power Bombs",
        "Red Brinstar Behind Alpha Power Bombs Missiles",
        "Red Brinstar Spazer",
        "Warehouse Brinstar Energy Tank",
        "Warehouse Brinstar Missiles",
        
        "Warehouse Brinstar Varia Suit",
        "Norfair Cathedral Missiles",
        "Norfair Ice Beam",
        "Norfair Crumble Shaft Missiles",
        "Norfair Crocomire Energy Tank",
        "Norfair Hi-Jump Boots",
        "Norfair Crocomire Escape Missiles",
        "Norfair Hi-Jump Missiles",
        
        "Norfair Hi-Jump Energy Tank",
        "Norfair Crocomire Power Bombs",
        "Norfair Crocomire Cosine Missiles",
        "Norfair Grapple Missiles",
        "Norfair Grapple Beam",
        "Norfair Bubble Mountain Reserve Tank",
        "Norfair Bubble Mountain Reserve Missiles",
        "Norfair Bubble Mountain Grapple Missiles",
        
        "Norfair Bubble Mountain Missiles",
        "Norfair Speedboost Missiles",
        "Norfair Speed Booster",
        "Norfair Wave Beam Missiles",
        "Norfair Wave Beam",
        "Norfair Golden Torizo Missiles",
        "Norfair Golden Torizo Super Missiles",
        
        "Norfair Mickey Mouse Missiles",
        "Norfair Springball Maze Missiles",
        "Norfair Lower Escape Power Bombs",
        "Norfair Power Bombs of Shame",
        "Norfair FrankerZ Missiles",
        "Norfair Ridley Energy Tank",
        "Norfair Screw Attack",
        
        "Norfair Dark Room Energy Tank",
        
        "Wrecked Ship Spooky Missiles",
        "Wrecked Ship Reserve Tank",
        "Wrecked Ship Bowling Missiles",
        "Wrecked Ship Robot Missiles",
        "Wrecked Ship Energy Tank",
        "Wrecked Ship West Super Missiles",
        "Wrecked Ship East Super Missiles",
        "Wrecked Ship Gravity Suit",
        
        "Maridia Main Street Missiles",
        "Maridia Main Street Super Missiles",
        "Maridia Turtle Energy Tank",
        "Maridia Turtle Missiles",
        "Maridia Watering Hole Super Missiles",
        "Maridia Watering Hole Missiles",
        "Maridia Pseudo-Spark Missiles",
        "Maridia Plasma Beam",
        
        "Maridia West Sandtrap Missiles",
        "Maridia Reserve Tank",
        "Maridia East Sandtrap Missiles",
        "Maridia East Sandtrap Power Bombs",
        "Maridia Aqueduct Missiles",
        "Maridia Aqeuduct Super Misiles",
        "Maridia Springball",
        "Maridia Precious Missiles",
        
        "Maridia Botwoon Energy Tank",
        "Maridia Space Jump"]
    
    
    # Patch ROM.
    # This part of the code is ugly as sin, I apologize.
    for i in range(100):
        item = itemsInOrderList[i]
        # Write PLM Data.
        f.seek(HexHelper.hexToInt(itemPLMLocationList[i]))
        # If there is no item in this location, we should NOT try to calculate a PLM-type offset,
        # As this could give us an incorrect PLM ID.
        if (item == "No Item"):
            PLMID = HexHelper.hexToInt(itemPLMIDs[item])
            PLMHexadecimalID = bytes.fromhex(format(PLMID, 'x'))[::-1]
            f.write(PLMHexadecimalID)
            continue
        PLMID = HexHelper.hexToInt(itemPLMIDs[item]) + (HexHelper.hexToInt(itemPLMBlockTypeMultiplier) * itemPLMBlockTypeList[i])
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
        memoryBaseLocation = HexHelper.hexToInt("029A00") + (HexHelper.hexToInt(itemLocationList[i]) * 2) 
        f.seek(memoryBaseLocation)
        # TODO: Handle width and height separately.
        if item in itemMessageNonstandardSizes:
            f.write(bytes.fromhex("8000")[::-1])
            f.seek(memoryBaseLocation + HexHelper.hexToInt("400"))
            f.write(bytes.fromhex(itemMessageNonstandardSizes[item])[::-1])
        else:
            f.write(bytes.fromhex("8040")[::-1])
            f.seek(memoryBaseLocation + HexHelper.hexToInt("400"))
            f.write(bytes.fromhex("0040")[::-1])
        f.seek(memoryBaseLocation + HexHelper.hexToInt("200"))
        f.write(bytes.fromhex(itemMessageAddresses[item])[::-1])
        f.seek(memoryBaseLocation + HexHelper.hexToInt("600"))
        f.write(bytes.fromhex(itemMessageIDs[item])[::-1])
        f.seek(memoryBaseLocation + HexHelper.hexToInt("800"))
        # If item is meant for a different player, it will do nothing at all.
        # This is not the same as there not being an item in this position - 
        # The item will be there, it will just have no effect for the SM player.
        if itemHoldersInOrderList is not None and itemHoldersInOrderList[i] != playerName:
            f.write(HexHelper.hexToData(itemGetRoutineAddressesDict["No Item"]))
        else:
            f.write(HexHelper.hexToData(itemGetRoutineAddressesDict[item]))
            
    # Write spoiler log
    spoilerPath = filePath[:filePath.rfind(".")] + "_SPOILER.txt"
    print("Spoiler file generating at " + spoilerPath + "...")
    spoilerFile = open(spoilerPath, 'w')
    for i in range(100):
        spoilerFile.write(locationNamesList[i] + ": " + itemsInOrderList[i] + "\n")
    spoilerFile.close()

def patchROM(ROMFilePath, itemList = None, recipientList = None, **kwargs):
    # Open ROM File
    f = open(ROMFilePath, 'r+b', buffering = 0)
    # Open Patcher Data Output File
    patcherOutputPath = filePath[:filePath.rfind(".")] + "_PatcherData.json"
    patcherOutput = open(patcherOutputPath, 'w')
    patcherOutputJson = {"patcherData" : []}
    # Generate item placement if none has been provided.
    # This will give a warning message, as this is only appropriate for debugging patcher features.
    if itemList is None:
        itemList = generateVanillaItemPlacement()
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
    # routineAlpha = -alp
    # routineBeta  = -bta
    # routineGamma = -gma
    # routineDelta = -dlt
    routineAlpha = "8D1F1CC91C00F00AC914009006C91900B00160AF74FF7FC90100D01CAF7CFF7F8D1F1CA500DA48AF7EFF7F850068A20000FC0000FA8500605ADAA22000BF6ED87E9FCEFF7FCACAE00000D0F1AFD0FF7F38EFB0FF7FC90000F0278F8EFF7FA90100CF8EFF7FF01AC90080080A28D0F2A22000A90000EA9FAEFF7FCACAE00000D0F1A22000BFCEFF7F38FFAEFF7F9F8EFF7FCACAE00000D0ECA0F000A22000BF8EFF7FC90000D00A9838E91000A8CACA80EDBFCEFF7F9FAEFF7FBF8EFF7FC90100F004C84A80F7980A8F8EFF7FAABD00A08D1F1CFC00A2FA7A60"
    routineBeta  = "20-gmaA920008516B900009F00327EC8C8E8E8C616D0F160"
    routineGamma = "AD1F1CC91C00F00AC914009009C91900B004A0408060AF74FF7FC90100D006AF76FF7FA860DAAF8EFF7FAABF009A85A8FA60"
    routineDelta = "AD1F1CC91C00F00AC91400902AC91900B025AD1F1C3A0A85340A186534AABD9F868500BDA58638E50085094A8516A50918698000850960AF74FF7FC90100D016AF78FF7FA88400AF7AFF7F4A85160A18698000850960DAAF8EFF7FAABF009C85A88400BF009E854A85160A186980008509FA60"

    routines = [routineAlpha, routineBeta, routineGamma, routineDelta]
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
    
    # Now the dumb part. We create item pickup routines, one for each item in the game.
    # Yes it's dumb, but dumb works. This can probably be optimized later.
    itemGetRoutines      = []
    
    # Flags have their endianness reversed before being written.
    beamBitFlags         = ["1000", "0002", "0001", "0004", "0008"]
    equipmentBitFlags    = ["0001", "0002", "0004", "0008", "0100", "0200", "2000", "1000", "0020"]
    
    # These values could later be substituted to give different effects for SM players.
    # Note that bytes are ordered in little-endian format.
    missilesPerPack      = "0500"
    supersPerPack        = "0500"
    energyPerTank        = "6400"
    energyPerReserve     = "6400"
    powerBombsPerPack    = "0500"
    
    # Make all the get routines and templates.
    etankGet             = "ADC4091869-nrg8DC4098DC20960"
    reserveGet           = "ADD4091869-rsv8DD409ADC009D003EEC00960"
    missileGet           = "ADC8091869-msl8DC809ADC6091869-msl8DC60922CF998060"
    supersGet            = "ADCC091869-spr8DCC09ADCA091869-spr8DCA09220E9A8060"
    pbsGet               = "ADD0091869-pwb8DD009ADCE091869-pwb8DCE09221E9A8060"
    grappleGet           = "ADA2090900408DA209ADA4090900408DA409222E9A8060"
    xRayGet              = "ADA2090900808DA209ADA4090900808DA409223E9A8060"
    equipmentGetTemplate = "ADA20909-eqp8DA209ADA40909-eqp8DA40960"
    beamGetTemplate      = "A9-bem0DA8098DA809A9-bem0DA6098DA609A9-bem0A2908001CA609A9-bem4A2904001CA609228DAC9060"
    equipmentGets        = [equipmentGetTemplate] * len(equipmentBitFlags)
    beamGets             = [beamGetTemplate] * len(beamBitFlags)
    
    # Substitute references for literals.
    etankGet = etankGet.replace("-nrg", energyPerTank)
    reserveGet = reserveGet.replace("-rsv", energyPerReserve)
    missileGet = missileGet.replace("-msl", missilesPerPack)
    supersGet = supersGet.replace("-spr", supersPerPack)
    pbsGet = pbsGet.replace("-pwb", powerBombsPerPack)
    
    # Create individual routines from ASM templates.
    for i in range(len(equipmentGets)):
        equipmentGets[i] = (equipmentGets[i]).replace("-eqp", HexHelper.reverseEndianness(equipmentBitFlags[i]))
    for i in range(len(beamGets)):
        beamGets[i] = (beamGets[i]).replace("-bem", HexHelper.reverseEndianness(beamBitFlags[i]))
    
    
    
    # Construct the item routine list in the proper order.
    itemGetRoutines.append(etankGet)
    itemGetRoutines.append(missileGet)
    itemGetRoutines.append(supersGet)
    itemGetRoutines.append(pbsGet)
    itemGetRoutines.append(grappleGet)
    itemGetRoutines.append(xRayGet)
    itemGetRoutines.extend(equipmentGets[0:7])
    itemGetRoutines.extend(beamGets)
    itemGetRoutines.append(equipmentGets[7])
    itemGetRoutines.append(reserveGet)
    itemGetRoutines.append(equipmentGets[8])
    # This is a command that will do nothing, used for items that are meant to go to other players.
    # 60 is the RTS instruction. In other words when called it will immediately returned.
    itemGetRoutines.append("60")
    
    
    # Write them to memory and store their addresses in an ordered list.
    # This is critical, as we will use these addresses to store to a table that dictates
    # What an item will do when picked up.
    # We'll be appending them to the same place as messagebox code, so we'll keep the
    # Address and file pointer we had from before.
    itemGetRoutineAddresses = []
    for i in range(len(itemGetRoutines)):
        itemGetRoutineAddresses.append(HexHelper.reverseEndianness(inGameAddress))
        f.write(HexHelper.hexToData(itemGetRoutines[i]))
        inGameAddress   = HexHelper.intToHex(HexHelper.hexToInt(inGameAddress) + (len(itemGetRoutines[i]) // 2))
        currentAddress += int(len(itemGetRoutines[i]) // 2)
    
    # You shouldn't ever need to expand this, as this only concerns the actual effects
    # Of items for the SM player.
    itemGetRoutineAddressesDict = {
        "Energy Tank"             : itemGetRoutineAddresses[ 0],
        "Missile Expansion"       : itemGetRoutineAddresses[ 1],
        "Super Missile Expansion" : itemGetRoutineAddresses[ 2],
        "Power Bomb Expansion"    : itemGetRoutineAddresses[ 3],
        "Grapple Beam"            : itemGetRoutineAddresses[ 4],
        "X-Ray Scope"             : itemGetRoutineAddresses[ 5],
        "Varia Suit"              : itemGetRoutineAddresses[ 6],
        "Spring Ball"             : itemGetRoutineAddresses[ 7],
        "Morph Ball"              : itemGetRoutineAddresses[ 8],
        "Screw Attack"            : itemGetRoutineAddresses[ 9],
        "Hi-Jump Boots"           : itemGetRoutineAddresses[10],
        "Space Jump"              : itemGetRoutineAddresses[11],
        "Speed Booster"           : itemGetRoutineAddresses[12],
        "Charge Beam"             : itemGetRoutineAddresses[13],
        "Ice Beam"                : itemGetRoutineAddresses[14],
        "Wave Beam"               : itemGetRoutineAddresses[15],
        "Spazer Beam"             : itemGetRoutineAddresses[16],
        "Plasma Beam"             : itemGetRoutineAddresses[17],
        "Morph Ball Bombs"        : itemGetRoutineAddresses[18],
        "Reserve Tank"            : itemGetRoutineAddresses[19],
        "Gravity Suit"            : itemGetRoutineAddresses[20],
        "No Item"                 : itemGetRoutineAddresses[21]
    }
    
    itemRoutinesJsonOutput = []
    for (itemName, routineAddress) in itemGetRoutineAddressesDict.items():
        itemRoutinesJsonOutput.append({"itemName" : itemName, "routineAddress" : routineAddress})
        print(itemName + " has routine address " + routineAddress)
    patcherOutputJson["patcherData"].append({"itemRoutines" : itemRoutinesJsonOutput})
    
    # Sanity check.
    # If this trips I'm in deep trouble.
    # We are safe - for now.
    print("Free routine ROM in bank 85 begins at " + inGameAddress)
    if HexHelper.hexToInt(inGameAddress) > HexHelper.hexToInt("9A00"):
        print("ERROR: Routines written overlap with start of pickup tables in bank $85")
        return
    
    # Patch Item Placements into the ROM.
    placeItems(f, ROMFilePath, itemGetRoutineAddressesDict, itemList)
    
    # Modify/overwrite existing routines.
    overwriteRoutines = []
    overwriteRoutineAddresses = []
    
    # Modify Message Box Routines To Allow Customizable Behavior
    routineOverwriteAlpha = "20-alp"
    routineOverwriteBeta  = "20-gmaA20000B900009F00327EE8E8C8C8E04000D0F0A0000020B88220-bta60"
    routineOverwriteGamma = "20-dltEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEAEA"
    routineOverwriteDelta = "205A82"
    
    # Addresses to write routines to in Headerless ROM file.
    routineOverwriteAlphaAddress = "028086"
    routineOverwriteBetaAddress = "02825A"
    routineOverwriteGammaAddress = "0282E5"
    routineOverwriteDeltaAddress = "028250"    
    
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
            routineZeta = "9CE20DADDA09D017A906008D9F079C8B07ADEA098F08D87E22008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"
            
            routineZetaAddress = "016EB4"
            
            overwriteRoutines.extend([routineZeta])
            overwriteRoutineAddresses.extend([routineZetaAddress])
        elif introOptionChoice == "Skip Intro And Ceres":
            routineZeta = "9CE20DADDA09D0149C9F079C8B07ADEA098F08D87EAD520922008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"
            routineZetaAddress = "016EB4"
            if "customSaveStart" in kwargs:
                pass
        else:
            print("WARNING: Invalid option entered for introOptionChoice. Defaulting to vanilla intro behavior...")
        
        overwriteRoutines.extend([routineZeta])
        overwriteRoutineAddresses.extend([routineZetaAddress])
    
    
    overwriteRoutines.extend([routineOverwriteAlpha, routineOverwriteBeta, routineOverwriteGamma, routineOverwriteDelta])
    overwriteRoutineAddresses.extend([routineOverwriteAlphaAddress, routineOverwriteBetaAddress, routineOverwriteGammaAddress, routineOverwriteDeltaAddress])
    
    # Apply static patches.
    # Many of these patches are provided by community members - 
    # See top of document for details.
    
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