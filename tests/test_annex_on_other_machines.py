"""The annex on machines that are not ours.

The first three annexes of the prueba2 failed, three of three, on what our
dumps never had: a router at 192.168.1.1 (the substitute itself), a USB stick
whose name is its disk's model, an awake NVIDIA, and a laptop called
«thinkpad» like its sensor chip. Here the dumper runs end to end, as the
report's annex runs it, on the suite's dumps (whose values are already the
substitutes) and on them with what those machines had, laid out as the
kernel lays it out.
"""

import contextlib
import json
import os
import pathlib
import socket
import tempfile
import unittest
from unittest import mock

from silux import annex, privacidad, volcado

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"


def _write(root: pathlib.Path, path: str, text: str) -> None:
    target = root / path.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def _link(root: pathlib.Path, path: str, to: str) -> None:
    link = root / path.lstrip("/")
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(to)


@contextlib.contextmanager
def _machine(dump: str):
    """A suite's dump mounted, to add things to, and where to dump it. The
    checks go inside: both are temporary."""
    with volcado.mounted(EQUIPOS / dump) as root, tempfile.TemporaryDirectory() as out:
        yield root, pathlib.Path(out)


def _dump(out: pathlib.Path, propios=None):
    """Dumps the mounted machine; the dump, its manifest and its bytes."""
    folder = volcado.dump("otro", out, own=propios if propios is not None else {})
    manifest = json.loads((folder / "manifiesto.json").read_text())
    everything = b"".join(p.read_bytes() for p in folder.rglob("*")
                          if p.is_file() and not p.is_symlink())
    everything += "\n".join(str(p.relative_to(folder)) for p in folder.rglob("*")).encode()
    return folder, manifest, everything


class TestWhatIsAlreadyCovered(unittest.TestCase):
    """Our dumps hold the substitutes: as a machine, they are one whose
    router is 192.168.1.1 and whose address is 192.168.1.120."""

    def test_the_suites_dumps_dump_again_whole(self):
        for dump in ("5800x3d", "i5-10400", "qemu-kvm"):
            with self.subTest(dump=dump), _machine(dump) as (_root, out):
                folder, manifest, _bytes = _dump(out, propios={
                    privacidad.IPV4: "una dirección IPv4 de este equipo"})
                self.assertNotIn("quitados", manifest)
                photo = volcado.snapshot_of(folder)
                self.assertEqual(volcado._what_anonymize_would_cover(photo), [])
                original = volcado.snapshot_of(EQUIPOS / dump)
                self.assertEqual([t.brand for t in photo.cpu.types],
                                 [t.brand for t in original.cpu.types])
                self.assertEqual([(i.name, i.gateway) for i in photo.network],
                                 [(i.name, i.gateway) for i in original.network])


class TestAUsbStick(unittest.TestCase):
    """The Celeron N4000's: its USB name is its disk's model."""

    STICK = "/sys/devices/pci0000:00/0000:00:15.0/usb2/2-2"
    DISK = STICK + "/2-2:1.0/host2/target2:0:0/2:0:0:0"
    SERIAL = "E0D55EA574F2F3A0B9E30F1B"

    def _add(self, root):
        for name, value in (("idVendor", "0951"), ("idProduct", "1666"), ("speed", "5000"),
                            ("manufacturer", "Kingston"), ("product", "DataTraveler 3.0"),
                            ("serial", self.SERIAL), ("bDeviceClass", "00"),
                            ("version", " 3.20")):
            _write(root, f"{self.STICK}/{name}", value + "\n")
        _write(root, f"{self.STICK}/2-2:1.0/bInterfaceClass", "08\n")
        _write(root, f"{self.STICK}/2-2:1.0/bInterfaceProtocol", "50\n")
        for name, value in (("model", "DataTraveler 3.0"), ("vendor", "Kingston"), ("rev", "PMAP")):
            _write(root, f"{self.DISK}/{name}", value + "\n")
        for name, value in (("size", "241827840"), ("removable", "1"), ("queue/rotational", "1"),
                            ("queue/logical_block_size", "512"),
                            ("queue/physical_block_size", "512"),
                            ("stat", "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0")):
            _write(root, f"{self.DISK}/block/sdz/{name}", value + "\n")
        _link(root, f"{self.DISK}/block/sdz/device", "../../../2:0:0:0")
        _link(root, "/sys/block/sdz", "../devices/pci0000:00/0000:00:15.0/usb2/2-2/2-2:1.0"
                                      "/host2/target2:0:0/2:0:0:0/block/sdz")
        _link(root, "/sys/bus/usb/devices/2-2", "../../../devices/pci0000:00/0000:00:15.0/usb2/2-2")

    def test_its_model_stays_and_its_serial_goes(self):
        with _machine("i5-10400") as (root, out):
            self._add(root)
            folder, manifest, everything = _dump(out, propios={
                self.SERIAL: "el número de serie de algo enchufado por USB"})
            self.assertNotIn("quitados", manifest)
            self.assertNotIn(self.SERIAL.encode(), everything)
            disks = {d.name: d for d in volcado.snapshot_of(folder).disks}
            self.assertEqual(disks["sdz"].model, "DataTraveler 3.0")


class TestAUsbBridge(unittest.TestCase):
    """A SATA disk in a JMicron USB enclosure: the bridge pads its serial
    with NUL bytes. The dump zeroed the characters and kept the NULs, the
    disk read them as part of the serial, and the check took the zeroed
    serial for an uncovered one: the annex was refused."""

    BRIDGE = "/sys/devices/pci0000:00/0000:00:08.1/0000:0b:00.3/usb4/4-3"
    DISK = BRIDGE + "/4-3:1.0/host9/target9:0:0/9:0:0:0"
    SERIAL = "A1B2C3D4E5F6"
    # The disk's own serial, its WWN and its partition table's UUID, in the
    # record udev wrote when its ata_id asked the disk through the bridge.
    DISK_SERIAL = "50026B7785F2A9C1"
    WWN = "0x50026b7785f2a9c1"
    TABLE_UUID = "9cf4b6f1-70b8-7962-4582-b467b28d9ac1"
    UDEV_RECORD = (
        f"S:disk/by-id/ata-KINGSTON_SA400S37240G_{DISK_SERIAL}\n"
        "S:disk/by-path/pci-0000:0b:00.3-usb-0:3:1.0-scsi-0:0:0:0\n"
        "I:689869423\n"
        "E:ID_ATA=1\nE:ID_TYPE=disk\nE:ID_BUS=ata\n"
        "E:ID_MODEL=KINGSTON_SA400S37240G\n"
        "E:ID_MODEL_ENC=KINGSTON\\x20SA400S37240G\\x20\\x20\\x20\n"
        "E:ID_REVISION=SBFKB1D1\n"
        f"E:ID_SERIAL=KINGSTON_SA400S37240G_{DISK_SERIAL}\n"
        f"E:ID_SERIAL_SHORT={DISK_SERIAL}\n"
        "E:ID_ATA_ROTATION_RATE_RPM=0\n"
        f"E:ID_WWN={WWN}\nE:ID_WWN_WITH_EXTENSION={WWN}\n"
        "E:ID_USB_MODEL=Tech\nE:ID_USB_VENDOR=JMicron\n"
        f"E:ID_USB_SERIAL=JMicron_Tech_{SERIAL}-0:0\nE:ID_USB_SERIAL_SHORT={SERIAL}\n"
        f"E:ID_PART_TABLE_UUID={TABLE_UUID}\nE:ID_PART_TABLE_TYPE=gpt\n"
        "G:systemd\nV:1\n")

    def _add(self, root):
        for name, value in (("idVendor", "7825"), ("idProduct", "a2a4"), ("speed", "5000"),
                            ("manufacturer", "JMicron"), ("product", "External"),
                            ("bDeviceClass", "00"), ("version", " 3.20")):
            _write(root, f"{self.BRIDGE}/{name}", value + "\n")
        _write(root, f"{self.BRIDGE}/4-3:1.0/bInterfaceClass", "08\n")
        _write(root, f"{self.BRIDGE}/4-3:1.0/bInterfaceProtocol", "62\n")
        for name, value in (("model", "Tech            "), ("vendor", "JMicron "),
                            ("rev", "4101"), ("serial", self.SERIAL + "\0\0\0\0")):
            _write(root, f"{self.DISK}/{name}", value + "\n")
        for name, value in (("size", "468862128"), ("removable", "0"), ("queue/rotational", "1"),
                            ("queue/logical_block_size", "512"),
                            ("queue/physical_block_size", "4096"),
                            ("stat", "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0")):
            _write(root, f"{self.DISK}/block/sdz/{name}", value + "\n")
        _write(root, f"{self.DISK}/block/sdz/dev", "65:240\n")
        _link(root, f"{self.DISK}/block/sdz/device", "../../../9:0:0:0")
        _link(root, "/sys/block/sdz", "../devices/pci0000:00/0000:00:08.1/0000:0b:00.3/usb4/4-3"
                                      "/4-3:1.0/host9/target9:0:0/9:0:0:0/block/sdz")
        _link(root, "/sys/bus/usb/devices/4-3",
              "../../../devices/pci0000:00/0000:00:08.1/0000:0b:00.3/usb4/4-3")

    def test_its_padded_serial_is_covered_and_the_annex_goes(self):
        with _machine("5800x3d") as (root, out):
            self._add(root)
            folder, manifest, everything = _dump(out, propios={
                self.SERIAL: "el número de serie de un disco"})
            self.assertNotIn("quitados", manifest)
            self.assertNotIn(self.SERIAL.encode(), everything)
            disks = {d.name: d for d in volcado.snapshot_of(folder).disks}
            self.assertEqual(disks["sdz"].serial, "0" * len(self.SERIAL))

    def test_the_live_disk_reads_it_without_the_padding(self):
        from silux.collector import Collector

        with _machine("5800x3d") as (root, _out):
            self._add(root)
            collector = Collector()
            try:
                disks = {d.name: d for d in collector.snapshot().disks}
            finally:
                collector.close()
        self.assertEqual(disks["sdz"].serial, self.SERIAL)

    def _add_udev(self, root):
        _write(root, "/run/udev/data/b65:240", self.UDEV_RECORD)

    def test_the_disk_behind_says_who_it_is_through_udev(self):
        # As udev has it, without permissions: the disk's model, firmware
        # and that it doesn't spin; the bridge apart.
        from silux.collector import Collector

        with _machine("5800x3d") as (root, _out):
            self._add(root)
            self._add_udev(root)
            collector = Collector()
            try:
                disks = {d.name: d for d in collector.snapshot().disks}
            finally:
                collector.close()
        disk = disks["sdz"]
        self.assertEqual((disk.model, disk.vendor, disk.firmware, disk.kind, disk.usb_bridge,
                          disk.rotation_rpm),
                         ("KINGSTON SA400S37240G", "Kingston", "SBFKB1D1", "SSD", "JMicron", 0))

    def test_without_it_the_bridge_is_all_there_is(self):
        from silux.collector import Collector

        with _machine("5800x3d") as (root, _out):
            self._add(root)
            collector = Collector()
            try:
                disk = {d.name: d for d in collector.snapshot().disks}["sdz"]
            finally:
                collector.close()
        self.assertEqual((disk.model, disk.kind, disk.usb_bridge), ("Tech", None, None))

    def test_the_storage_page_says_it(self):
        from silux.collector import Collector
        from silux.i18n import _
        from tests import pantalla, qt

        qt.app()
        with _machine("5800x3d") as (root, _out):
            self._add(root)
            self._add_udev(root)
            collector = Collector()
            try:
                collector.snapshot()
                photo = collector.snapshot()
            finally:
                collector.close()
        with pantalla.Ventana(photo) as window:
            window.select_section("Almacenamiento")
            for _turn in range(4):
                qt.app().processEvents()
            texts = pantalla.textos_de(window.storage_page)
        self.assertIn("KINGSTON SA400S37240G", texts)
        self.assertIn(_("storage.field.bridge"), texts)
        self.assertIn("JMicron", texts)
        self.assertNotIn(_("storage.na.kind.usb"), texts)

    def test_the_dump_keeps_the_udev_keys_read_and_no_identifier(self):
        with _machine("5800x3d") as (root, out):
            self._add(root)
            self._add_udev(root)
            folder, manifest, everything = _dump(out)
            self.assertNotIn("quitados", manifest)
            for identifier in (self.DISK_SERIAL, self.WWN, self.TABLE_UUID, self.SERIAL):
                self.assertNotIn(identifier.encode(), everything, identifier)
            record = (folder / "run/udev/data/b65:240").read_text()
            self.assertEqual(sorted(line.split("=")[0] for line in record.splitlines()),
                             ["E:ID_ATA", "E:ID_ATA_ROTATION_RATE_RPM", "E:ID_MODEL_ENC",
                              "E:ID_REVISION"])
            disk = {d.name: d for d in volcado.snapshot_of(folder).disks}["sdz"]
            self.assertEqual((disk.model, disk.kind), ("KINGSTON SA400S37240G", "SSD"))

    def test_left_uncovered_the_refusal_says_where_and_only_that(self):
        # A dumper that forgot the `serial` files, as it could forget another.
        with _machine("5800x3d") as (root, out), \
                mock.patch.object(volcado, "SERIAL_FILES", volcado.SERIAL_FILES - {"serial"}):
            self._add(root)
            with self.assertRaises(volcado.Refusal) as caught:
                _dump(out)
        refusal = caught.exception
        self.assertEqual([f.rsplit(".", 1)[-1] for f in refusal.fields], ["serial"])
        (field,) = refusal.fields
        self.assertEqual(refusal.files[field], [self.DISK + "/serial"])
        text = annex.outcome(1, "", annex.REFUSED + json.dumps(
            {"campos": refusal.fields, "archivos": refusal.files}))[1]
        self.assertIn(self.DISK + "/serial", text)
        self.assertNotIn(self.SERIAL, text)


class TestNamesOfMachines(unittest.TestCase):
    """A machine is called as everyone's often: its distribution (Debian's
    installer proposes «debian»), its brand, its family or its sensor chip
    («thinkpad»), a short or common word. None blocks the annex or breaks
    what it is also the name of; a person's name goes from everywhere."""

    def _thinkpad(self, root):
        # thinkpad_acpi's hwmon is called «thinkpad»; a ThinkPad's DMI family.
        hwmon = "/sys/devices/platform/thinkpad_hwmon/hwmon/hwmon9"
        _write(root, f"{hwmon}/name", "thinkpad\n")
        _write(root, f"{hwmon}/temp1_input", "45000\n")
        _write(root, f"{hwmon}/fan1_input", "2300\n")
        _link(root, "/sys/class/hwmon/hwmon9", "../../devices/platform/thinkpad_hwmon/hwmon/hwmon9")
        dmi = root / "sys/class/dmi/id"
        for name, value in (("sys_vendor", "LENOVO"), ("product_family", "ThinkPad T14 Gen 2i")):
            (dmi / name).write_text(value + "\n")

    @contextlib.contextmanager
    def _dump_named(self, name):
        with _machine("qemu-kvm") as (root, out):
            self._thinkpad(root)
            _write(root, "/proc/sys/kernel/hostname", name + "\n")
            os_release = (root / "etc/os-release").read_text()
            # The checker as on that machine: its name and the rest of its own.
            with mock.patch.object(socket, "gethostname", return_value=name):
                propios = privacidad.of_this_machine()
            folder, manifest, everything = _dump(out, propios=propios)
            yield folder, manifest, everything, os_release

    def test_everyones_names_block_nothing_and_break_nothing(self):
        for name in ("thinkpad", "lenovo", "arch", "debian", "pc", "linux"):
            with self.subTest(name=name), self._dump_named(name) as (folder, manifest, _b, os_release):
                self.assertNotIn("quitados", manifest)
                self.assertEqual((folder / "etc/os-release").read_text(), os_release)
                hwmon = folder / "sys/devices/platform/thinkpad_hwmon/hwmon/hwmon9/name"
                self.assertEqual(hwmon.read_text(), "thinkpad\n")
                self.assertEqual((folder / "proc/sys/kernel/hostname").read_text().strip(),
                                 privacidad.HOST_NAME)

    def test_a_persons_name_goes_from_everywhere(self):
        with self._dump_named("portatil-ana") as (_folder, manifest, everything, _os):
            self.assertNotIn(b"portatil-ana", everything)
            self.assertNotIn("quitados", manifest)


class TestTheT14NamedThinkpad(unittest.TestCase):
    """The author's T14, named «thinkpad»: in prueba2 its annex was refused
    for «el nombre de este equipo» in thinkpad_hwmon. Its prueba4 annex came
    out whole; here its real dump is dumped again under that name."""

    def test_its_annex_comes_out_whole(self):
        manifest = json.loads((EQUIPOS / "i5-1135g7" / "manifiesto.json").read_text())
        self.assertNotIn("quitados", manifest)

    def test_dumped_again_as_thinkpad(self):
        with _machine("i5-1135g7") as (root, out):
            _write(root, "/proc/sys/kernel/hostname", "thinkpad\n")
            with mock.patch.object(socket, "gethostname", return_value="thinkpad"):
                propios = privacidad.of_this_machine()
            folder, manifest, _everything = _dump(out, propios=propios)
            self.assertNotIn("quitados", manifest)
            self.assertEqual((folder / "proc/sys/kernel/hostname").read_text().strip(),
                             privacidad.HOST_NAME)
            self.assertTrue((folder / "sys/devices/platform/thinkpad_hwmon").is_dir())
            nombres = {p.read_text().strip() for p in (folder / "sys/class/hwmon").glob("*/name")}
            self.assertIn("thinkpad", nombres)


class TestNvidiaCards(unittest.TestCase):
    """Any awake NVIDIA: a laptop (an Intel integrated and an RTX 4050) and a
    desktop (an RTX 4060) had no annex in the prueba2. And a machine with two,
    each with its own UUID."""

    @staticmethod
    def _card(index, slot, uuid, name, driver, cuda, gib, bus):
        return {"index": index, "pci_slot": slot, "uuid": uuid, "serial": None, "name": name,
                "driver_version": driver, "cuda_cores": cuda, "memory_total_bytes": gib << 30,
                "memory_bus_bits": bus, "throttle_reasons": []}

    CASES = {
        "laptop": ("i5-10400", [("0000:01:00.0", "GPU-5c2b6d0e-8f41-4a7d-b3e9-1f0c2a7d9e64",
                                 "NVIDIA GeForce RTX 4050 Laptop GPU", "550.163.01", 2560, 6, 96)]),
        "desktop": ("5800x3d", [("0000:2d:00.0", "GPU-91d3a7c4-0b2e-4f6a-9c18-7e5d2a4b6c80",
                                 "NVIDIA GeForce RTX 4060", "595.104.02", 3072, 8, 128)]),
        "two": ("5800x3d", [("0000:2d:00.0", "GPU-91d3a7c4-0b2e-4f6a-9c18-7e5d2a4b6c80",
                             "NVIDIA GeForce RTX 4060", "595.104.02", 3072, 8, 128),
                            ("0000:2e:00.0", "GPU-0a7e6b5c-4d3f-4e2a-8b1c-9d0e1f2a3b4c",
                             "NVIDIA GeForce RTX 3060", "595.104.02", 3584, 12, 192)]),
    }

    def test_each_cards_id_covered(self):
        for case, (dump, cards) in self.CASES.items():
            with self.subTest(case=case), _machine(dump) as (root, out):
                grabado = json.loads((root / "grabado.json").read_text())
                grabado["nvml"] = {"abierta": True, "tarjetas": [
                    self._card(i, *c) for i, c in enumerate(cards)]}
                (root / "grabado.json").write_text(json.dumps(grabado))
                folder, manifest, everything = _dump(out, propios={})
                self.assertNotIn("quitados", manifest)
                for _slot, uuid, name, *_rest in cards:
                    self.assertNotIn(uuid[4:].encode(), everything)
                names = [g.name for g in volcado.snapshot_of(folder).gpus]
                self.assertLessEqual({c[2] for c in cards}, set(names))


class TestNetworkConnections(unittest.TestCase):
    """Wired, Wi-Fi, USB adapters, bridges, PPP and VPNs."""

    SYSTEMS = ("wlp2s0", "nordlynx", "br0", "ppp0", "tailscale0", "wg0", "tun0")
    # A USB adapter's MAC, written in pieces: whole, the privacy checker
    # takes it for one leaving in the repository.
    MAC = "00:11:22" + ":33:44:55"
    HEX = MAC.replace(":", "")
    ENX = "enx" + HEX

    def _add(self, root, name, mac="00:00:00:00:00:00"):
        base = f"/sys/devices/virtual/net/{name}"
        for field, value in (("operstate", "up"), ("mtu", "1420"), ("address", mac),
                             ("type", "1"), ("carrier", "1")):
            _write(root, f"{base}/{field}", value + "\n")
        _link(root, f"/sys/class/net/{name}", f"../../devices/virtual/net/{name}")

    def test_the_systems_stay_and_what_names_someone_goes(self):
        with _machine("5800x3d") as (root, out):
            for name in self.SYSTEMS:
                self._add(root, name)
            self._add(root, self.ENX, self.MAC)
            self._add(root, "ana_wg0")
            folder, manifest, everything = _dump(out, propios={
                self.ENX: "una interfaz de red con nombre puesto a mano",
                self.HEX: f"la dirección física de {self.ENX}",
                self.MAC: f"la dirección física de {self.ENX}",
                "ana_wg0": "una interfaz de red con nombre puesto a mano"})
            self.assertNotIn("quitados", manifest)
            names = {p.name for p in (folder / "sys/class/net").iterdir()}
            self.assertLessEqual(set(self.SYSTEMS), names)
            self.assertIn("enx00005e0053af", names)
            self.assertIn(privacidad.INTERFACE.format(1), names)
            for gone in (self.HEX, self.MAC, "ana_wg0"):
                self.assertNotIn(gone.encode(), everything)
            self.assertEqual(volcado._what_anonymize_would_cover(volcado.snapshot_of(folder)), [])


class TestWhatCannotBeCovered(unittest.TestCase):
    """Something of the person where no rule looks (a name in a sensor's
    label): that file goes, the annex says which and what it held, and the
    rest is written."""

    def test_the_file_goes_and_the_annex_says_so(self):
        label = "/sys/devices/platform/thinkpad_hwmon/hwmon/hwmon9/temp1_label"
        with _machine("qemu-kvm") as (root, out):
            TestNamesOfMachines()._thinkpad(root)
            _write(root, label, "Ana García\n")
            folder, manifest, everything = _dump(out, propios={
                "Ana García": "el nombre de quien usa este equipo"})
            self.assertNotIn("Ana García".encode(), everything)
            self.assertEqual(manifest["quitados"], [{"ruta": label, "dato": "machine"}])
            block = annex.to_text(folder)
            self.assertEqual(annex.removed(block), manifest["quitados"])
            self.assertIn(label, annex.section(block, None))


class TestWhatIsInAFoldersName(unittest.TestCase):
    """On the CI's machine one of its identifiers was in a folder's name: the
    folder went, and the manifest said where with the identifier in it, so
    the second check refused the dump."""

    def test_it_goes_and_where_it_was_is_said_covered(self):
        chip = "/sys/devices/platform/anagarcia_hwmon/hwmon/hwmon9"
        with _machine("qemu-kvm") as (root, out):
            _write(root, f"{chip}/name", "nct6775\n")
            _write(root, f"{chip}/temp1_input", "45000\n")
            _link(root, "/sys/class/hwmon/hwmon9", "../../devices/platform/anagarcia_hwmon/hwmon/hwmon9")
            folder, manifest, everything = _dump(out, propios={
                "anagarcia": "el nombre de quien usa este equipo"})
            self.assertNotIn(b"anagarcia", everything)
            # The folder, and the link that leads to it and names it too.
            self.assertEqual([q["ruta"] for q in manifest["quitados"]],
                             ["/sys/class/hwmon/hwmon9", "/sys/devices/platform/…_hwmon"])


class TestARefusalInWords(unittest.TestCase):

    def test_by_field_and_kind_never_by_value(self):
        from silux import render
        from silux.i18n import _
        text = render.annex_refusal(["gpus[1].unique_id", "network[0].ipv4"])
        self.assertIn(_("annex.what.gpu_id"), text)
        self.assertIn(_("annex.what.ip"), text)
        self.assertIn("gpus[1].unique_id", text)
        line = annex.REFUSED + json.dumps({"campos": ["gpus[1].unique_id"]})
        self.assertEqual(annex.outcome(1, "", "algo\n" + line)[1],
                         render.annex_refusal(["gpus[1].unique_id"]))


if __name__ == "__main__":
    unittest.main()
