"""KiCad netlist data model and parser."""
from __future__ import annotations

import dataclasses
import hashlib
import re
from pathlib import Path

from .sexpr import iter_blocks, property_map, quoted_value


@dataclasses.dataclass(frozen=True)
class PinConnection:
    pin: str
    function: str
    pin_type: str
    net: str


@dataclasses.dataclass
class Component:
    reference: str
    value: str
    footprint: str
    datasheet: str
    fields: dict[str, str]
    pins: dict[str, PinConnection] = dataclasses.field(default_factory=dict)

    @property
    def manufacturer(self) -> str:
        return self.fields.get("MANUFACTURER", self.fields.get("Manufacturer", ""))

    @property
    def manufacturer_part(self) -> str:
        return self.fields.get("MANUFACTURER PART", self.fields.get("Manufacturer Part", ""))

    @property
    def supplier_number(self) -> str:
        for key in ("LCSC Part #", "SUPPLIER PART", "LCSC", "LCSC Part"):
            value = self.fields.get(key, "")
            if value:
                return value
        return ""

    def net(self, pin: int | str) -> str:
        key = str(pin)
        if key not in self.pins:
            raise KeyError(f"{self.reference} has no connected physical pin {key}")
        return self.pins[key].net


@dataclasses.dataclass
class DesignMetadata:
    source: str
    export_date: str
    tool: str
    version: str
    sha256: str


@dataclasses.dataclass
class Design:
    path: Path
    metadata: DesignMetadata
    components: dict[str, Component]
    nets: dict[str, list[PinConnection]]

    def require_component(self, reference: str) -> Component:
        try:
            return self.components[reference]
        except KeyError as exc:
            raise KeyError(f"Required reference {reference} is absent from {self.path}") from exc

    def require_net(self, net: str) -> list[PinConnection]:
        try:
            return self.nets[net]
        except KeyError as exc:
            raise KeyError(f"Required net {net!r} is absent from {self.path}") from exc

    def refs(self, prefix: str) -> list[str]:
        def key(ref: str) -> tuple[str, int, str]:
            match = re.fullmatch(r"([A-Za-z]+)(\d+)(.*)", ref)
            if not match:
                return ref, 0, ""
            return match.group(1), int(match.group(2)), match.group(3)

        return sorted((ref for ref in self.components if ref.startswith(prefix)), key=key)


def parse_netlist(path: Path) -> Design:
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")

    metadata = DesignMetadata(
        source=quoted_value(text, "source"),
        export_date=quoted_value(text, "date"),
        tool=quoted_value(text, "tool"),
        version=quoted_value(text, "version"),
        sha256=hashlib.sha256(raw).hexdigest(),
    )

    components: dict[str, Component] = {}
    for block in iter_blocks(text, "comp"):
        reference = quoted_value(block, "ref")
        if not reference:
            continue
        components[reference] = Component(
            reference=reference,
            value=quoted_value(block, "value"),
            footprint=quoted_value(block, "footprint"),
            datasheet=quoted_value(block, "datasheet"),
            fields=property_map(block),
        )

    nets: dict[str, list[PinConnection]] = {}
    for net_block in iter_blocks(text, "net"):
        net_name = quoted_value(net_block, "name")
        if not net_name:
            continue
        connections: list[PinConnection] = []
        for node_block in iter_blocks(net_block, "node"):
            reference = quoted_value(node_block, "ref")
            pin = quoted_value(node_block, "pin")
            if not reference or not pin:
                continue
            connection = PinConnection(
                pin=pin,
                function=quoted_value(node_block, "pinfunction"),
                pin_type=quoted_value(node_block, "pintype"),
                net=net_name,
            )
            connections.append(connection)
            if reference in components:
                components[reference].pins[pin] = connection
        nets[net_name] = connections

    if not components or not nets:
        raise ValueError(f"{path} did not parse as a populated KiCad exported netlist")
    return Design(path=path, metadata=metadata, components=components, nets=nets)
