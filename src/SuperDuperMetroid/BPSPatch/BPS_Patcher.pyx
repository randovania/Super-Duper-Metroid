import sys
import os
import zlib

from libc.stdio cimport FILE, fopen, fclose, fseek, fgetc, SEEK_SET
from libc.stdio cimport fclose, fputc, ftell

# Converts a hexadecimal string to a base 10 integer.
def hexToInt(hexToConvert):
    return int(hexToConvert, 16)

# Converts an integer to a hexadecimal string.
def intToHex(intToConvert):
    return (hex(intToConvert)[2:]).upper()

# Converts binary data to a hexadecimal string.
def dataToHex(dataToConvert):
    return "".join("{:02x}".format(x) for x in dataToConvert).upper()

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

class BPSInfo:
    def __init__(self, sourceSize, targetSize, metadataSize):
        self.sourceSize = sourceSize
        self.targetSize = targetSize
        self.metadataSize = metadataSize

cdef class BPSIOHandling:
    @staticmethod
    cdef long applyCommandChunks(char *bpsPath, char *sourcePath, char *targetPath, int bpsHeaderOffset, int bpsSize):
        cdef long outputOffset = 0
        cdef long sourceRelativeOffset = 0
        cdef long targetRelativeOffset = 0

        cdef long offset
        cdef int invert
        cdef int byte

        cdef long data
        cdef int command
        cdef long length

        cdef int bpsFooterSize = 12

        cdef FILE *bpsFile = fopen(bpsPath, "rb")
        cdef FILE *sourceFile = fopen(sourcePath, "rb")
        cdef FILE *targetFile = fopen(targetPath, "w+b")

        fseek(bpsFile, bpsHeaderOffset, SEEK_SET)
        while ftell(bpsFile) < bpsSize - bpsFooterSize:
            data = BPSIOHandling.readVariableLengthNumber(bpsFile)
            command = data & 3
            length = (data >> 2) + 1
            if command == 0:
                #Source Read
                fseek(sourceFile, outputOffset, SEEK_SET)
                for i in range(length):
                    fputc(fgetc(sourceFile), targetFile)
                outputOffset += length
                continue
            elif command == 1:
                #Target Read
                for i in range(length):
                    fputc(fgetc(bpsFile), targetFile)
                outputOffset += length
                continue
            elif command == 2:
                #Source Copy
                offset = BPSIOHandling.readVariableLengthNumber(bpsFile)
                invert = 0
                if offset & 1 > 0:
                    invert = 1
                offset >>= 1
                if invert == 1:
                    offset *= -1
                sourceRelativeOffset += offset
                fseek(sourceFile, sourceRelativeOffset, SEEK_SET)
                for i in range(length):
                    fputc(fgetc(sourceFile), targetFile)
                sourceRelativeOffset += length
                outputOffset += length
                continue
            elif command == 3:
                #Target Copy
                offset = BPSIOHandling.readVariableLengthNumber(bpsFile)
                invert = 0
                if offset & 1 > 0:
                    invert = 1
                offset >>= 1
                if invert == 1:
                    offset *= -1
                targetRelativeOffset += offset
                # We do this one byte at a time because it is is possible to read and rewrite from bytes that were written in the same command.
                for i in range(length):
                    fseek(targetFile, targetRelativeOffset, SEEK_SET)
                    byte = fgetc(targetFile)
                    fseek(targetFile, outputOffset, SEEK_SET)
                    fputc(byte, targetFile)
                    targetRelativeOffset += 1
                    outputOffset += 1
        fclose(bpsFile)
        fclose(sourceFile)
        fclose(targetFile)

    @staticmethod
    cdef long readVariableLengthNumber(FILE *bpsFile):
        cdef long value = 0
        cdef long shift = 1
        cdef int byte
        while (True):
            byte = fgetc(bpsFile)
            #print(byte)
            value += (byte & 0x7F) * shift
            if (byte & 0x80 > 0):
                break
            shift <<= 7
            value += shift
        return value

class BPSPatcher:
    # Read the first 4 bytes to verify that this is an BPS file.
    @staticmethod
    def verifyFormat(bpsFile):
        verificationBytes = dataToHex(bpsFile.read(4))
        if verificationBytes == "42505331": # Spells out "BPS1
            return True
        else:
            return False

    @staticmethod
    def readHeader(bpsFile):
        sourceSize = BPSPatcher.readVariableLengthNumber(bpsFile)
        targetSize = BPSPatcher.readVariableLengthNumber(bpsFile)
        metadataSize = BPSPatcher.readVariableLengthNumber(bpsFile)
        return BPSInfo(sourceSize, targetSize, metadataSize)

    # Apply an BPS patch to a ROM, given the paths of an BPS file and a ROM file.
    @staticmethod
    def applyBPSPatch(bpsPath, romPath, targetPath):
        cdef char* bpsCString
        cdef char* romCString
        cdef char* targetCString
        print(f"Applying patch from file {bpsPath}...")
        bpsFile = open(bpsPath, 'rb', buffering = 0)
        bpsSize = os.path.getsize(bpsPath)
        if BPSPatcher.verifyFormat(bpsFile):
            patchInfo = BPSPatcher.readHeader(bpsFile)
            # Skip metadata
            bpsFile.seek(patchInfo.metadataSize, os.SEEK_CUR)
            dataStartPosition = bpsFile.tell()
            bpsFile.close()
            bpsCString = bpsPath
            romCString = romPath
            targetCString = targetPath
            BPSIOHandling.applyCommandChunks(bpsCString, romCString, targetCString, dataStartPosition, bpsSize)

            print("Finished assembling target file.")
            # Compute the CRC-32 hashes for appropriate data and check against data held in the footer.
            bpsFile = open(bpsPath, 'rb', buffering = 0)

            BPSPatcher.verifyFileIntegrity(romPath, targetPath, bpsFile)
            bpsFile.close()
        else:
            print(f"CRITICAL ERROR: Provided BPS file {bpsPath} does not match the format specification!")
        bpsFile.close()

    # Reads a "number" starting at the bpsFile's current file pointer.
    @staticmethod
    def readVariableLengthNumber(bpsFile):
        value = 0
        shift = 1
        while (True):
            byte = hexToInt(dataToHex(bpsFile.read(1)))
            #print(byte)
            value += (byte & hexToInt("7F")) * shift
            if byte & hexToInt("80") > 0:
                break
            shift <<= 7
            value += shift
        #print(f"Result: {value}")
        return value

    @staticmethod
    def verifyFileIntegrity(romPath, targetPath, bpsFile):
        # Seek to the beginning of the footer
        bpsFile.seek(-12, 2)
        # Nab the CRCs from the bps file
        romFooterCRC = hexToInt(reverseEndianness(dataToHex(bpsFile.read(4))))
        targetFooterCRC = hexToInt(reverseEndianness(dataToHex(bpsFile.read(4))))
        bpsFooterCRC = hexToInt(reverseEndianness(dataToHex(bpsFile.read(4))))
        # Calculate CRCs on the data
        romFile = open(romPath, 'rb', buffering = 0)
        targetFile = open(targetPath, 'rb', buffering = 0)

        romCRC = BPSPatcher.crc32(romFile)
        targetCRC = BPSPatcher.crc32(targetFile)
        bpsCRC = BPSPatcher.crc32(bpsFile, 4)
        # Compare calculated CRCs to those stored within the bps file.
        failedCheck = False
        if romFooterCRC != romCRC:
            print(f"ERROR: ROM failed CRC check.\n\tExpected CRC: {padHex(intToHex(romFooterCRC), 4)}\n\tCalculated CRC: {padHex(intToHex(romCRC), 4)}")
        if targetFooterCRC != targetCRC:
            print(f"ERROR: Target File failed CRC check.\n\tExpected CRC: {padHex(intToHex(targetFooterCRC), 4)}\n\tCalculated CRC: {padHex(intToHex(targetCRC), 4)}")
        if bpsFooterCRC != bpsCRC:
            print(f"ERROR: BPS Patch failed CRC check.\n\tExpected CRC: {padHex(intToHex(bpsFooterCRC), 4)}\n\tCalculated CRC: {padHex(intToHex(bpsCRC), 4)}")

    # numBytesToExclude is the number of bytes at the end of the file which are not counted for computing the crc.
    # the bpsCRC included does not hash itself, for obvious reasons, so it is necessary for that.
    @staticmethod
    def crc32(file, numBytesToExclude = 0):
        hash = 0
        # Used to ensure file gets cut off properly after reaching the limit.
        checkRead = b''
        file.seek(0, os.SEEK_END)
        fileSize = file.tell()
        chunkSize = 65536
        numChunks = fileSize // chunkSize
        remainder = fileSize % chunkSize
        file.seek(0)
        if remainder < numBytesToExclude:
            remainder = chunkSize - (numBytesToExclude - remainder)
            numChunks -= 1
        else:
            remainder -= numBytesToExclude
        for i in range(numChunks):
            s = file.read(chunkSize)
            hash = zlib.crc32(s, hash)
        s = file.read(remainder)
        hash = zlib.crc32(s, hash)
        return hash

if __name__ == "__main__":
    print("Enter path to BPS file.")
    bpsPath = str.encode(input())
    print("Enter path to ROM file.")
    romPath = str.encode(input())
    print("Enter path for output file")
    targetPath = str.encode(input())
    BPSPatcher.applyBPSPatch(bpsPath, romPath, targetPath)
