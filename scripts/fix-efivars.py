#!/usr/bin/env python3

import argparse
import base64
import gzip
import logging
import struct
import sys
import uuid
from typing import Dict, Iterable, Tuple, Union

import XenAPI

# Repair tool to delete variables affected by the varstored append data limit issue.
# It also deletes the dbx variable if it contains the varstored-1.2.0-3.1 dbx, in order to allow existing VMs to receive
# dbx updates from Microsoft.
# Serialization code adapted from varstored.

# The first 1024 bytes of the decapsulated dbx content from varstored-1.2.0-3.1.xcpng8.3.x86_64.
# To recreate:
# varstore-set <VM UUID> d719b2cb-3d3a-4596-a3bc-dad00e67656f dbx 0x27 dbx.auth
# varstore-get <VM UUID> d719b2cb-3d3a-4596-a3bc-dad00e67656f dbx | head -c 1024 | gzip -n -9 | base64
XCPNG_DBX_20250729 = gzip.decompress(
    base64.b64decode("""
H4sIAAAAAAACA1MTO3LQJ2CSw5qVjj/NJjtr6MxmAAMDIH6k+mB2tGOs89rEbDtO/0O9DVtuZhru
52X6O3GZnORFf9klQc9yNzn0rEjwdZSflDqfC139V/3mxb/m/L42ib9IQ+X2E2ZXk0vRrewq2dZT
a9fkSZ+rQld/9OaNhW2PTuhyrl+llV+vV9zOa5fyXceP4316ZVYLP/9edPVSb1p2eOekLhVSWLmv
sHFakIEib9K1yzYeM+dka0Zpc7Ghqz+8cpYb75KUBeGHI3Kbz339so5ju4Bl5dtOoxLdD2+DedLQ
1Uf8niL1fuqiSOfNv+NVBRbct3/iE3EyjmsHS7tmacbq6YXo6oMnHl70W1CRadkquTuq68ofzo/N
5zzL+W5TwEyl/WcjJ71CV39NTbRONquw+6DK6t5FNbtT2XUWWFVnq9buPb034Vvc54vo6i8kv9H4
Vrcr+GOK7v7a/8bHFmvdbZufIPxPTE/H6OPpp7no6jWPvQ7aYmO1sFvnxtu8FQk1721+Pdz1TzC1
NObTM5EWLxd09RN+P+fLvGbs0GsnzpNhdHvTJc4H6qrq97fZel6aWrTsiw+6eoH8Na/Ov/nrZ2Bd
8qVhQcOMRxcatCfn9x0vOaf4WawtYw66enE/K+5o52PL2HdfdvBnNZGzPW+ZlH5uyo+tfHrKK29N
4kFXrz3zvJqT3qR/ZvH7vQ/zqnPkzHvoXZX/3+W3fvYExsyZlujq9Qomprct+14cKL9cQn41v2zB
1vBjRnorlTetuLxTO3B9Lbp6+3Oz59+3+zA3JGjDz7gnjYe2f8gtsSquLAztKxDOOmdXjK7e/QxH
ovojtlltD6yy3+tcEfhxNCo3+7aZYsZhaZ3HWlH30dUXfpqQf0nJsy5ksVvSapXpf04IKJTzfxXO
ePn45v7Tf5NL0dU33bY+t+Ubh/O5udMPX2w/OzvS8aztCwG+iHztW2Hm4fHp6Oq7rnlEfpy69Wvv
+lVTuLMS09dcq+rI63ebnCJepHg00nUnuvrevkWd559zybCvLk49rfEu8O1lm08A2feG8QAEAAA=
""")
)

DB_MAGIC = b"VARS"
DB_HEADER_LEN = len(DB_MAGIC) + struct.calcsize("<IQQ")
assert DB_HEADER_LEN == 24
DB_VERSION = 2

HEADER_STRUCT = struct.Struct("<4sIQQ")
assert HEADER_STRUCT.size == 24

ANCILLARY_DATA_LEN_V2 = 8 + 0x104
ANCILLARY_DATA_LEN = ANCILLARY_DATA_LEN_V2

PPI_VDATA = struct.Struct("<I256s")

EFI_VARIABLE_TAIL = struct.Struct("<16sI16s32s")
VARIABLE_SIZE = struct.calcsize("<QQ") + EFI_VARIABLE_TAIL.size
assert VARIABLE_SIZE == 84

EFI_VARIABLE_NON_VOLATILE = 0x00000001

NVRAM_KEY = "EFI-variables"

# Limits specified by varstored v1.3.0
NAME_LIMIT = 4096  # Maximum length of name
DATA_LIMIT = 57344  # Maximum length of a single variable
TOTAL_LIMIT = 131072  # Maximum total storage

VARIABLE_SIZE_OVERHEAD = 128
MAX_VARIABLE_COUNT = TOTAL_LIMIT / VARIABLE_SIZE_OVERHEAD


def unserialize(format: Union[str, bytes], buf: bytes, offset: int = 0):
    return (buf[struct.calcsize(format) :],) + struct.unpack_from(format, buf, offset)


def unserialize_struct(s: struct.Struct, buf: bytes, offset: int = 0):
    return (buf[s.size :],) + s.unpack_from(buf, offset)


def unserialize_data(buf: bytes, rem: int, limit: int):
    buf, buflen = unserialize("<Q", buf)
    logging.debug(f"    nextlen {buflen}")

    if buflen > rem:
        logging.debug("    nextlen > rem")
        return None
    if buflen == 0:
        logging.debug("    nextlen == 0")
        return None
    if buflen > limit:
        logging.debug("    ! nextlen > limit")

    var = buf[:buflen]
    buf = buf[buflen:]

    return buf, var


class EfiVariable:
    def __init__(
        self,
        name: bytes,
        data: bytes,
        guid: bytes,
        attr: int,
        timestamp: bytes,
        cert: bytes,
    ) -> None:
        self.name = name
        self.data = data
        self.guid = guid
        self.attr = attr
        self.timestamp = timestamp
        self.cert = cert

        self.display_name = self.name.decode("utf-16le")
        self.display_guid = uuid.UUID(bytes_le=self.guid)

    @staticmethod
    def unserialize_variables(buf: bytes, count: int, rem: int):
        for i in range(count):
            logging.debug(f"variable {i}")

            if rem < VARIABLE_SIZE:
                raise ValueError(f"invalid rem {rem}")
            rem -= VARIABLE_SIZE

            _name = unserialize_data(buf, rem, NAME_LIMIT)
            if _name is None:
                raise ValueError("invalid name")
            buf, name = _name
            logging.debug(f"    name {name.decode('utf-16le')}")
            rem -= len(name)

            _data = unserialize_data(buf, rem, DATA_LIMIT)
            if _data is None:
                raise ValueError("invalid data")
            buf, data = _data
            logging.debug(f"    datalen {len(data)}")
            rem -= len(data)

            buf, guid, attr, timestamp, cert = unserialize_struct(EFI_VARIABLE_TAIL, buf)

            variable = EfiVariable(
                name=name,
                data=data,
                guid=guid,
                attr=attr,
                timestamp=timestamp,
                cert=cert,
            )

            logging.debug(
                f"    {variable.display_guid} {variable.display_name} "
                f"len {len(variable.data)} attr 0x{variable.attr:x} timestamp {variable.timestamp}"
            )
            logging.debug(f"    content: {base64.b64encode(data).decode()}")
            logging.debug(f"    rem {rem}")

            yield variable

        if rem:
            raise ValueError(f"More data than expected: {rem}")


class EfiVariables:
    def __init__(
        self,
        version: int,
        variables: Iterable[EfiVariable],
        mor_key: bytes,
        ppi_vdata: Tuple[int, bytes],
    ) -> None:
        self.version = version
        self.variables = list(variables)
        if version == 2:
            assert len(mor_key) == 8
            self._mor_key = mor_key
            assert ppi_vdata is not None
            assert len(ppi_vdata[1]) == 256
            self._ppi_vdata = ppi_vdata
        else:
            self._mor_key = b""
            self._ppi_vdata = (0, b"")

    @property
    def mor_key(self) -> bytes:
        assert self.version == 2
        return self._mor_key

    @property
    def ppi_vdata(self) -> Tuple[int, bytes]:
        assert self.version == 2
        return self._ppi_vdata

    @staticmethod
    def xapidb_parse_blob(buf: bytes):
        buflen = len(buf)

        (buf, magic, version, count, datalen) = unserialize_struct(HEADER_STRUCT, buf)
        if magic != DB_MAGIC:
            raise ValueError("Invalid init magic")
        logging.debug(f"version {version}, count {count}, datalen {datalen}")
        if version > DB_VERSION:
            raise ValueError("Unsupported init version")
        if count > MAX_VARIABLE_COUNT:
            raise ValueError(f"Invalid variable count {count} > %{MAX_VARIABLE_COUNT}")

        buflen -= DB_HEADER_LEN

        mor_key = b""
        ppi_vdata = (0, b"")
        if version == 2:
            if buflen < ANCILLARY_DATA_LEN_V2:
                raise ValueError("Init file size is invalid")

            mor_key = buf[:8]
            buf = buf[8:]

            buf, ppi_vdata_idx, ppi_vdata_func = unserialize_struct(PPI_VDATA, buf)
            ppi_vdata = ppi_vdata_idx, ppi_vdata_func

            buflen -= ANCILLARY_DATA_LEN_V2

        return EfiVariables(
            version=version,
            variables=EfiVariable.unserialize_variables(buf, count, buflen),
            mor_key=mor_key,
            ppi_vdata=ppi_vdata,
        )

    def data_len(self, only_nv: bool):
        result = 0

        for variable in self.variables:
            if only_nv and (variable.attr & EFI_VARIABLE_NON_VOLATILE) == 0:
                continue

            result += VARIABLE_SIZE
            result += len(variable.name)
            result += len(variable.data)

        return result

    def xapidb_serialize_variables(self, only_nv: bool):
        out = b""

        data_len = self.data_len(only_nv)
        logging.debug(f"total data_len {data_len}")
        out += HEADER_STRUCT.pack(DB_MAGIC, self.version, len(self.variables), data_len)
        if self.version == 2:
            out += self.mor_key
            out += PPI_VDATA.pack(*self.ppi_vdata)

        for variable in self.variables:
            if only_nv and (variable.attr & EFI_VARIABLE_NON_VOLATILE) == 0:
                continue

            variable_bytes = b""

            variable_bytes += struct.pack("<Q", len(variable.name))
            variable_bytes += variable.name

            variable_bytes += struct.pack("<Q", len(variable.data))
            variable_bytes += variable.data

            variable_bytes += EFI_VARIABLE_TAIL.pack(variable.guid, variable.attr, variable.timestamp, variable.cert)

            logging.debug(f"variable {variable.display_name} len {len(variable_bytes)}")
            out += variable_bytes

        supposed_size = HEADER_STRUCT.size + data_len
        if self.version == 2:
            supposed_size += len(self.mor_key) + PPI_VDATA.size
        assert supposed_size == len(out)
        return out


def filter_variables(variables: Iterable[EfiVariable], keep_old_dbx: bool):
    for variable in variables:
        if len(variable.data) > DATA_LIMIT:
            print(
                f"Variable exceeds limit: {variable.display_guid} {variable.display_name} "
                f"({len(variable.data)} > {DATA_LIMIT})",
                file=sys.stderr,
            )
        elif (
            not keep_old_dbx
            and variable.display_guid == uuid.UUID("d719b2cb-3d3a-4596-a3bc-dad00e67656f")
            and variable.display_name == "dbx"
            and XCPNG_DBX_20250729 in variable.data
        ):
            print("Variable dbx contains old content", file=sys.stderr)
        else:
            yield variable


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("vm_uuid", help="UUID of VM to scan or fix")
    parser.add_argument("--fix", action="store_true", help="fix the NVRAM (instead of just printing invalid variables)")
    parser.add_argument(
        "--keep-old-dbx",
        action="store_true",
        help="when fixing the NVRAM, don't delete the dbx even if it contains the old blob from varstored 1.2.0-3.1",
    )
    parser.add_argument(
        "--backup", help="backup NVRAM file path (default 'VM_UUID.efivars.b64')", metavar="BACKUP_PATH"
    )
    parser.add_argument("--overwrite-backup", action="store_true", help="overwrite existing backup")
    parser.add_argument("--dry-run", action="store_true", help="don't fix the NVRAM for real; just take a backup")
    parser.add_argument("-v", "--verbose", action="store_true", help="print detailed info")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    session = XenAPI.xapi_local()
    session.xenapi.login_with_password("root", "", XenAPI.API_VERSION_1_2, "fix-efivars.py")

    try:
        vm_ref = session.xenapi.VM.get_by_uuid(args.vm_uuid)
        nvram: Dict[str, str] = session.xenapi.VM.get_NVRAM(vm_ref)

        efivars = nvram.get(NVRAM_KEY)
        if not efivars:
            raise ValueError("EFI vars are empty")

        if args.fix:
            backup_path = args.backup or f"{args.vm_uuid}.efivars.b64"
            print(f"Backing up existing variables to {backup_path}", file=sys.stderr)
            with open(backup_path, "w" if args.overwrite_backup else "x") as backup:
                backup.write(efivars)

        parsed = EfiVariables.xapidb_parse_blob(base64.b64decode(efivars, validate=True))
        valid_variables = list(filter_variables(parsed.variables, args.keep_old_dbx))
        delete_count = len(parsed.variables) - len(valid_variables)

        if args.fix:
            parsed.variables = valid_variables
            fixed = parsed.xapidb_serialize_variables(False)
            verify = EfiVariables.xapidb_parse_blob(fixed)
            assert verify is not None
            assert len(verify.variables) == len(parsed.variables)
            for var_verify, var_parsed in zip(verify.variables, parsed.variables):
                assert var_verify.name == var_parsed.name
                assert var_verify.guid == var_parsed.guid
                assert var_verify.attr == var_parsed.attr

            if not args.dry_run and delete_count > 0:
                session.xenapi.VM.remove_from_NVRAM(vm_ref, NVRAM_KEY)
                session.xenapi.VM.add_to_NVRAM(vm_ref, NVRAM_KEY, base64.b64encode(fixed).decode())

            print(
                f"Deleted {delete_count} variable(s) in VM {args.vm_uuid}{' (dry-run)' if args.dry_run else ''}",
                file=sys.stderr,
            )
        else:
            print(
                f"Found {delete_count} variable(s) to delete in VM {args.vm_uuid}",
                file=sys.stderr,
            )
    finally:
        session.xenapi.logout()
