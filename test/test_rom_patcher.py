from SuperDuperMetroid import ROM_Patcher

romSize = 3145728

# endAddress is excluded
def isFileByteRangeEmpty(f, emptyByte, startAddress, endAddress):
    foundNonEmptyByte = False
    f.seek(startAddress)
    bytes = f.read(endAddress - startAddress)
    for byte in bytes:
        if byte != emptyByte[0]:
            print(byte)
            print(emptyByte)
            foundNonEmptyByte = True
            break
    print(foundNonEmptyByte)
    return not foundNonEmptyByte


# Creates a blank file to test writes with
def createBlankFile(fileName, emptyByte):
    f = open(fileName, "wb+")
    f.write(b"\0" * romSize)
    f.seek(0)
    return f


# Converts a hexadecimal string to binary data.
def hexToData(hexToConvert):
    return bytes.fromhex(hexToConvert)


def test_genVanillaGame():
    result = ROM_Patcher.genVanillaGame()
    assert len(result) == 100


def test_addStartingInventory():
    f = None
    try:
        fileName = "startingInventoryTest.bin"
        f = createBlankFile(fileName, b"\0")

        startingItems = [
            ROM_Patcher.PickupPlacementData(1, -1, "Morph Ball"),
            ROM_Patcher.PickupPlacementData(1, -1, "Gravity Suit"),
        ]
        itemGetRoutineAddressesDict = {
            "Morph Ball": 0x1234,
            "Gravity Suit": 0x5678,
        }

        ROM_Patcher.addStartingInventory(f, startingItems, itemGetRoutineAddressesDict)

        # Assert the presence of routines
        assert isFileByteRangeEmpty(f, b"\0", 0, 0x02FFFB)
        # functionToReturnProperly
        assert not isFileByteRangeEmpty(f, b"\0", 0x02FFFB, (0x02FFFB + 5))
        assert isFileByteRangeEmpty(f, b"\0", (0x02FFFB + 5), 0x08763A)
        # awardStartingInventoryRoutine
        assert not isFileByteRangeEmpty(f, b"\0", 0x08763A, (0x08763A + 43))
        assert isFileByteRangeEmpty(f, b"\0", (0x08763A + 43), 0x1C0000)
        # Assert the presence of starting inventory data
        assert not isFileByteRangeEmpty(f, b"\0", 0x1C0000, 0x1C0007)
        assert isFileByteRangeEmpty(f, b"\0", 0x1C0007, romSize)

        # Assert correctness of routines
        functionToReturnProperly = hexToData("A95FF6486B")
        awardStartingInventoryRoutine = hexToData(
            "AF0080B8AAE00000F020DAE220A99048C220A9FAFF48E220A98548C2208A0AAABF0080B8486BFACA80DB6B"
        )
        f.seek(0x02FFFB)
        returnFunctionBytes = f.read(5)
        f.seek(0x08763A)
        awardItemsRoutineBytes = f.read(43)

        assert functionToReturnProperly == returnFunctionBytes
        assert awardStartingInventoryRoutine == awardItemsRoutineBytes

        # Assert the correctness of routine data
        f.seek(0x1C0000)
        startingInventoryBytes = f.read(6)
        assert (bytearray(startingInventoryBytes) == bytes([0x02, 0x00, 0x33, 0x12, 0x77, 0x56])) or (
            bytes(startingInventoryBytes) == bytes([0x02, 0x00, 0x77, 0x56, 0x33, 0x12])
        )
    except Exception:
        f.close()
        raise


def test_writeSaveInitializationRoutines_SkipIntroAndCeres():
    f = None
    try:
        fileName = "startSaveTest_IntroCeres.bin"
        f = createBlankFile(fileName, b"\0")

        ROM_Patcher.writeSaveInitializationRoutines(f, "Skip Intro And Ceres")

        # Assert the presence of routines
        assert isFileByteRangeEmpty(f, b"\0", 0, 0x016EB4)
        assert not isFileByteRangeEmpty(f, b"\0", 0x016EB4, (0x016EB4 + 70))
        assert isFileByteRangeEmpty(f, b"\0", (0x016EB4 + 70), romSize)
        # Assert the correctness of routine data
        f.seek(0x016EB4)
        introAndCeresDefaultStart = hexToData(
            "9CE20DADDA09D01E223AF690A900008D9F07A900008D8B07ADEA098F08D87EAD520922008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"
        )
        startSave = f.read(70)
        assert introAndCeresDefaultStart == startSave
    except Exception:
        f.close()
        raise


def test_writeSaveInitializationRoutines_CustomSaveStart():
    f = None
    try:
        fileName = "startSaveTest_CustomSaveStart.bin"
        f = createBlankFile(fileName, b"\0")

        ROM_Patcher.writeSaveInitializationRoutines(f, "Skip Intro And Ceres", ["Brinstar", 0])

        # Assert the presence of routines
        assert isFileByteRangeEmpty(f, b"\0", 0, 0x016EB4)
        assert not isFileByteRangeEmpty(f, b"\0", 0x016EB4, (0x016EB4 + 70))
        assert isFileByteRangeEmpty(f, b"\0", (0x016EB4 + 70), romSize)
        # Assert the correctness of routine data
        f.seek(0x016EB4)
        customSaveStart = hexToData(
            "9CE20DADDA09D01E223AF690A901008D9F07A900008D8B07ADEA098F08D87EAD520922008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"
        )
        startSave = f.read(70)
        assert customSaveStart == startSave
    except Exception:
        f.close()
        raise


def test_writeSaveInitializationRoutines_SkipIntroOnly():
    f = None
    try:
        fileName = "startSaveTest_Intro.bin"
        f = createBlankFile(fileName, b"\0")

        ROM_Patcher.writeSaveInitializationRoutines(f, "Skip Intro")

        # Assert the presence of routines
        assert isFileByteRangeEmpty(f, b"\0", 0, 0x016EB4)
        assert not isFileByteRangeEmpty(f, b"\0", 0x016EB4, (0x016EB4 + 64))
        assert isFileByteRangeEmpty(f, b"\0", (0x016EB4 + 64), romSize)
        # Assert the correctness of routine data
        f.seek(0x016EB4)
        introSkipStart = hexToData(
            "9CE20DADDA09D01B223AF690A906008D9F079C8B07ADEA098F08D87E22008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"
        )
        startSave = f.read(64)
        assert introSkipStart == startSave
    except Exception:
        f.close()
        raise


def test_writeCrateriaWakeupRoutine():
    f = None
    try:
        fileName = "crateriaWakeupTest.bin"
        f = createBlankFile(fileName, b"\0")

        ROM_Patcher.writeCrateriaWakeupRoutine(f)

        # Assert the presence of routines
        assert isFileByteRangeEmpty(f, b"\0", 0, 0x07E652)
        assert not isFileByteRangeEmpty(f, b"\0", 0x07E652, (0x07E652 + 19))
        assert isFileByteRangeEmpty(f, b"\0", (0x07E652 + 19), romSize)
        # Assert the correctness of routine data
        f.seek(0x07E652)
        crateriaWakeupRoutine = hexToData("AF73D87E290400F007BD0000AA4CE6E5E8E860")
        wakeupBytes = f.read(19)
        assert crateriaWakeupRoutine == wakeupBytes
    except Exception:
        f.close()
        raise


def test_writeMultiworldRoutines():
    f = None
    try:
        fileName = "multiRoutineTest.bin"
        f = createBlankFile(fileName, b"\0")

        ROM_Patcher.writeMultiworldRoutines(f)

        # Assert the presence of routines
        assert isFileByteRangeEmpty(f, b"\0", 0, 0x01AD66)
        assert not isFileByteRangeEmpty(f, b"\0", 0x01AD66, (0x01AD66 + 22))
        assert isFileByteRangeEmpty(f, b"\0", (0x01AD66 + 22), 0x087FF0)
        assert not isFileByteRangeEmpty(f, b"\0", 0x087FF0, (0x087FF0 + 13))
        assert isFileByteRangeEmpty(f, b"\0", (0x087FF0 + 13), romSize)
        # Assert the correctness of routine data
        f.seek(0x01AD66)
        itemGetRoutine = hexToData("AD1F1C22808085A900008F74FF7FAF80FF7F8D420A6B")
        itemGetBytes = f.read(22)
        f.seek(0x087FF0)
        executeMultiworldRoutine = hexToData("E220A98348C220AF72FF7F486B")
        multiExecBytes = f.read(13)
        assert itemGetRoutine == itemGetBytes
        assert executeMultiworldRoutine == multiExecBytes
    except Exception:
        f.close()
        raise
