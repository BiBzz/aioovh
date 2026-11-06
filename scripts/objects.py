"""Object layer: business namespaces, collections, references and loaded objects."""

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import yaml
from operations import (
    GENERATED_MARKER,
    RESERVED_FIELD_NAMES,
    ROOT,
    Module,
    Operation,
    Param,
    docstring,
    identifier,
    pascal,
    snake,
    write,
)
from pydantic import BaseModel

PACKAGE = ROOT / "src" / "aioovh"
MAPPING = ROOT / "mapping.yaml"
COVERAGE = ROOT / "docs" / "coverage.md"
TREE = ROOT / "docs" / "objects.md"
CURSOR_HEADERS = {"X-Pagination-Cursor", "X-Pagination-Size"}
STANDARD_MEMBERS = {"update", "delete", "refresh"}
MODEL_ATTRIBUTES = {name for name in dir(BaseModel) if not name.startswith("__")}
RESERVED_MEMBERS = {
    "list",
    "dict",
    "set",
    "type",
    "str",
    "int",
    "float",
    "bool",
    "all",
    "filter",
    "ids",
    "create",
}
BUILTIN_NAMES = {
    "Any",
    "Instant",
    "Date",
    "list",
    "dict",
    "str",
    "int",
    "float",
    "bool",
    "bytes",
    "None",
}


INVARIABLE = {
    "vps",
    "nas",
    "sms",
    "dns",
    "kms",
    "status",
    "access",
    "address",
    "rancher",
    "xdsl",
    "fax",
    "nutanix",
    "vmware",
    "telephony",
    "analytics",
    "ssl",
}


def singular(name: str) -> str:
    head, _, last = name.rpartition("_")
    if last in INVARIABLE:
        return name
    if last == "ips":
        return f"{head}_ip" if head else "ip"
    for plural, single in (("ies", "y"), ("sses", "ss"), ("xes", "x"), ("ches", "ch")):
        if name.endswith(plural):
            return name[: -len(plural)] + single
    if name.endswith("s") and not name.endswith(("ss", "us", "is", "os")):
        return name[:-1]
    return name


def segment_name(segment: str) -> str:
    return identifier(snake(segment))


@dataclass
class Root:
    path: str
    segments: list[str]
    namespace: str
    name: str | None
    area: bool
    scope: dict[str, str]
    prefix: str = ""


@dataclass
class Call:
    operation: Operation
    module: Module
    scope: dict[str, str] = field(default_factory=dict)


@dataclass
class Resource:
    namespace: str
    root: str
    segments: tuple[str, ...]
    parent: "Resource | None"
    module: Module
    scope: dict[str, str] = field(default_factory=dict)
    listing_only: bool = False
    prefix: str = ""
    params: Counter[str] = field(default_factory=Counter)
    name: str = ""
    class_name: str = ""
    model: str | None = None
    load: Call | None = None
    listing: Call | None = None
    create: Call | None = None
    item_calls: dict[str, Call] = field(default_factory=dict)
    collection_calls: dict[str, Call] = field(default_factory=dict)
    children: list["Resource"] = field(default_factory=list)

    @property
    def param(self) -> str:
        return self.params.most_common(1)[0][0] if self.params else ""

    @property
    def key_names(self) -> list[str]:
        chain = [] if self.parent is None else self.parent.key_names
        return chain if self.listing_only else [*chain, self.param]

    @property
    def path(self) -> str:
        return f"{self.namespace}:{self.root}:{'/'.join(self.segments)}"


@dataclass
class NamespacePlan:
    name: str
    roots: list[Resource] = field(default_factory=list)
    calls: dict[str, Call] = field(default_factory=dict)
    load: Call | None = None
    modules: list[Module] = field(default_factory=list)


@dataclass
class Plan:
    namespaces: dict[str, NamespacePlan] = field(default_factory=dict)
    coverage: list[tuple[str, str, str]] = field(default_factory=list)


def path_segments(operation: Operation) -> list[str]:
    return [segment for segment in operation.path.split("/")[2:] if segment]


def model_fields(module: Module, class_name: str) -> dict[str, str]:
    """Field name to annotation-free wire name of a generated model, by class name."""
    for model_id, name in module.names.items():
        if name == class_name:
            properties = module.models[model_id].get("properties") or {}
            return {identifier(wire, RESERVED_FIELD_NAMES): wire for wire in properties}
    return {}


def model_classes(module: Module) -> set[str]:
    return {
        name
        for model_id, name in module.names.items()
        if "enum" not in module.models[model_id]
    }


class Builder:
    def __init__(self, modules: list[Module], mapping: dict[str, Any]) -> None:
        self.modules = modules
        self.mapping = mapping
        self.plan = Plan()
        self.roots = sorted(
            (
                Root(
                    path,
                    [s for s in path.split("/") if s],
                    spec["namespace"],
                    spec.get("name"),
                    bool(spec.get("area")),
                    dict(spec.get("scope") or {}),
                    str(spec.get("prefix") or ""),
                )
                for path, spec in mapping["roots"].items()
            ),
            key=lambda root: -len(root.segments),
        )
        self.resources: dict[tuple[str, str, tuple[str, ...]], Resource] = {}

    def match(self, segments: list[str]) -> Root | None:
        for root in self.roots:
            if segments[: len(root.segments)] == root.segments:
                return root
        return None

    def namespace(self, name: str) -> NamespacePlan:
        if name not in self.plan.namespaces:
            self.plan.namespaces[name] = NamespacePlan(name)
        return self.plan.namespaces[name]

    def place(self, call: Call, where: str) -> None:
        operation = call.operation
        self.plan.coverage.append(
            (
                f"{call.module.version}{call.module.resource}",
                f"{operation.http_method} {operation.path}",
                where,
            )
        )

    def split(
        self, call: Call
    ) -> tuple[Root, dict[str, str], list[tuple[str, str]], list[str]]:
        segments = path_segments(call.operation)
        root = self.match(segments)
        if root is None:
            raise SystemExit(f"mapping.yaml: no root for {call.operation.path}")
        scope = {
            part.strip("{}"): root.scope[part.strip("{}")]
            for part in root.segments
            if part.startswith("{") and part.strip("{}") in root.scope
        }
        rest = segments[len(root.segments) :]
        if not root.area:
            rest = [root.name or segment_name(root.segments[-1]), *rest]
        chain: list[tuple[str, str]] = []
        pending: list[str] = []
        for segment in rest:
            if segment.startswith("{"):
                name = "_".join(pending) or (chain[-1][0] if chain else "items")
                chain.append((name, segment.strip("{}")))
                pending = []
            else:
                pending.append(segment_name(segment))
        return root, scope, chain, pending

    def resource(
        self,
        root: Root,
        module: Module,
        chain: list[tuple[str, str]],
        scope: dict[str, str],
    ) -> Resource:
        parent = None
        for depth in range(1, len(chain) + 1):
            segments = tuple(name for name, _ in chain[:depth])
            key = (root.namespace, root.path, segments)
            if key not in self.resources:
                self.resources[key] = Resource(
                    root.namespace,
                    root.path,
                    segments,
                    parent,
                    module,
                    dict(scope),
                    prefix=root.prefix,
                )
                if parent is not None:
                    parent.children.append(self.resources[key])
            current = self.resources[key]
            current.params[chain[depth - 1][1]] += 1
            parent = current
        assert parent is not None
        return parent

    def build(self) -> Plan:
        calls = []
        for module in self.modules:
            if module.resource in self.mapping.get("raw_only", {}):
                for operation in module.operations:
                    self.place(
                        Call(operation, module),
                        "raw only: " + self.mapping["raw_only"][module.resource],
                    )
                continue
            for operation in module.operations:
                call = Call(operation, module)
                root, scope, chain, tail = self.split(call)
                call.scope = scope
                if chain:
                    self.resource(root, module, chain, scope)
                calls.append((call, root, scope, chain, tail))
        for call, root, scope, chain, tail in calls:
            self.assign(call, root, scope, chain, tail)
        self.name_resources()
        return self.plan

    def assign(
        self,
        call: Call,
        root: Root,
        scope: dict[str, str],
        chain: list[tuple[str, str]],
        tail: list[str],
    ) -> None:
        operation = call.operation
        namespace = self.namespace(root.namespace)
        if call.module not in namespace.modules:
            namespace.modules.append(call.module)
        verb = operation.http_method
        is_list = verb == "GET" and operation.response.startswith("list[")
        owner = (
            self.resources[(root.namespace, root.path, tuple(n for n, _ in chain))]
            if chain
            else None
        )
        if operation.status == "DEPRECATED":
            self.place(call, "raw only: deprecated")
            return
        needs_more = any(
            p.required and p.location not in ("path", "header")
            for p in operation.params
        )
        if not tail and owner is not None:
            if verb == "GET" and owner.load is None and not needs_more:
                owner.load = call
                owner.module = call.module
                self.place(call, f"await {owner.path}(...)")
                return
            standard = {
                "GET": "details",
                "PUT": "update",
                "DELETE": "delete",
                "PATCH": "edit",
                "POST": "submit",
            }[verb]
            if standard in owner.item_calls:
                standard = f"{standard}_details"
            owner.item_calls[standard] = call
            self.place(call, f"{owner.path}(...).{standard}()")
            return
        if not tail and owner is None:
            if verb == "GET" and namespace.load is None and not scope:
                namespace.load = call
                self.place(call, f"await {namespace.name}")
                return
            verb_name = {
                "PUT": "update",
                "POST": "submit",
                "DELETE": "delete",
                "GET": "get",
                "PATCH": "edit",
            }[verb]
            name = f"{verb_name}_{segment_name(root.segments[-1])}"
            self.add_call(namespace.calls, name, call)
            self.place(call, f"{namespace.name}.{name}()")
            return
        name = "_".join(tail)
        segments = (*[n for n, _ in chain], name)
        target = self.resources.get((root.namespace, root.path, segments))
        if target is not None and target.listing_only:
            target = None
        if target is not None:
            if is_list and target.listing is None:
                target.listing = call
                self.place(call, f"async for x in {target.path}")
                return
            if verb == "POST" and target.create is None:
                target.create = call
                self.place(call, f"{target.path}.create()")
                return
            member = self.member(target, f"{verb.lower()}_{name}", call)
            target.collection_calls[member] = call
            self.place(call, f"{target.path}.{member}()")
            return
        if is_list:
            listing = self.resources.get((root.namespace, root.path, segments))
            if listing is None:
                listing = Resource(
                    root.namespace,
                    root.path,
                    segments,
                    owner,
                    call.module,
                    dict(scope),
                    True,
                    root.prefix,
                )
                self.resources[(root.namespace, root.path, segments)] = listing
                if owner is not None:
                    owner.children.append(listing)
            if listing.listing is None:
                listing.listing = call
                self.place(call, f"async for x in {listing.path}")
                return
        prefix = {
            "GET": "",
            "PUT": "update_",
            "DELETE": "delete_",
            "POST": "",
            "PATCH": "edit_",
        }[verb]
        member = f"{prefix}{name}"
        listing = self.resources.get((root.namespace, root.path, segments))
        if (
            listing is not None
            and listing.listing_only
            and verb == "POST"
            and listing.create is None
        ):
            listing.create = call
            self.place(call, f"{listing.path}.create()")
            return
        if owner is not None:
            member = self.member(owner, member, call)
            if member in owner.item_calls:
                member = f"{member}_{verb.lower()}"
            owner.item_calls[member] = call
            self.place(call, f"{owner.path}(...).{member}()")
            return
        member = self.member(None, member, call, namespace.name)
        if root.prefix:
            member = f"{root.prefix}_{member}"
        self.add_call(namespace.calls, member, call)
        self.place(call, f"{namespace.name}.{member}()")

    def member(
        self, resource: Resource | None, name: str, call: Call, namespace: str = ""
    ) -> str:
        key = f"{resource.path if resource else namespace}:{name}"
        if key in self.mapping.get("members", {}):
            return str(self.mapping["members"][key])
        name = identifier(name)
        if (
            name in STANDARD_MEMBERS
            or name in MODEL_ATTRIBUTES
            or name in RESERVED_MEMBERS
        ):
            name = f"{name}_{call.operation.http_method.lower()}"
        return name

    @staticmethod
    def add_call(calls: dict[str, Call], name: str, call: Call) -> None:
        if name in calls:
            name = f"{name}_details"
        if name in calls:
            raise SystemExit(
                f"Two operations named {name}: {calls[name].operation.path}, {call.operation.path}"
            )
        calls[name] = call

    def name_resources(self) -> None:
        collections = self.mapping.get("collections", {})
        for resource in self.resources.values():
            if resource.parent is None:
                self.namespace(resource.namespace).roots.append(resource)
            default = segment_name(resource.segments[-1])
            if resource.prefix and resource.parent is None:
                default = f"{resource.prefix}_{default}"
            resource.name = str(collections.get(resource.path, default))
            resource.model = self.resource_model(resource)
            if (
                resource.load is not None
                and resource.load.operation.response != resource.model
            ):
                resource.item_calls.setdefault("details", resource.load)
                resource.load = None
        problems = []
        for namespace in self.plan.namespaces.values():
            counts = Counter(r.name for r in namespace.roots)
            for name, count in counts.items():
                if count > 1:
                    owners = sorted(r.path for r in namespace.roots if r.name == name)
                    problems.append(f"{namespace.name}.{name}: {', '.join(owners)}")
            for name in list(namespace.calls):
                if name in counts:
                    call = namespace.calls.pop(name)
                    namespace.calls[f"{name}_{call.operation.http_method.lower()}"] = (
                        call
                    )
        if problems:
            raise SystemExit(
                "Collections with the same name, rename them in mapping.yaml:\n  "
                + "\n  ".join(problems)
            )
        for namespace in self.plan.namespaces.values():
            everything = [
                r for r in self.resources.values() if r.namespace == namespace.name
            ]
            for resource in everything:
                base = pascal(singular(resource.name))
                resource.class_name = base
            names = Counter(r.class_name for r in everything)
            for resource in everything:
                if names[resource.class_name] > 1 and resource.parent is not None:
                    resource.class_name = (
                        pascal(singular(resource.parent.name)) + resource.class_name
                    )
            names = Counter(r.class_name for r in everything)
            for resource in everything:
                if names[resource.class_name] > 1:
                    resource.class_name = pascal("_".join(resource.segments))
                    if resource.listing_only:
                        resource.class_name += "Listing"
            names = Counter(r.class_name for r in everything)
            for resource in everything:
                if names[resource.class_name] > 1:
                    resource.class_name = (
                        pascal(resource.module.name) + resource.class_name
                    )
            names = Counter(r.class_name for r in everything)
            duplicates = sorted(name for name, count in names.items() if count > 1)
            if duplicates:
                raise SystemExit(
                    f"{namespace.name}: duplicate class names {duplicates}"
                )

    def resource_model(self, resource: Resource) -> str | None:
        if resource.listing_only:
            return None
        classes = model_classes(resource.module)
        if resource.load is not None and resource.load.operation.response in classes:
            return resource.load.operation.response
        if (
            resource.listing is not None
            and resource.listing.operation.response.startswith("list[")
        ):
            listed = resource.listing.operation.response[5:-1]
            if listed in model_classes(resource.listing.module):
                resource.module = resource.listing.module
                return listed
        return None


class Renderer:
    """Writes one namespace package: types.py, resources.py and __init__.py."""

    def __init__(
        self, plan: Plan, namespace: NamespacePlan, mapping: dict[str, Any]
    ) -> None:
        self.plan = plan
        self.namespace = namespace
        self.mapping = mapping
        self.public: dict[tuple[str, str], str] = {}
        self.bound: dict[tuple[str, str], Resource] = {}
        self.imports: dict[str, set[str]] = defaultdict(set)
        self.all_resources = self.collect()

    def collect(self) -> list[Resource]:
        found: list[Resource] = []

        def walk(resource: Resource) -> None:
            found.append(resource)
            for child in resource.children:
                walk(child)

        for root in self.namespace.roots:
            walk(root)
        for resource in found:
            if resource.model is not None:
                self.bound.setdefault(
                    (module_id(resource.module), resource.model), resource
                )
        return found

    def type_names(self) -> dict[tuple[str, str], str]:
        names: dict[tuple[str, str], str] = {}
        counts: Counter[str] = Counter()
        modules = self.namespace.modules
        for module in modules:
            for name in set(module.names.values()):
                if (module_id(module), name) not in self.bound:
                    counts[name] += 1
        reserved = {r.class_name for r in self.all_resources}
        reserved |= {
            f"{r.class_name}{suffix}"
            for r in self.all_resources
            for suffix in ("Ref", "Collection")
        }
        reserved.add(namespace_class_name(self.namespace.name))
        originals = {name for module in modules for name in module.names.values()}
        taken: set[str] = set()
        for module in modules:
            for name in sorted(set(module.names.values())):
                if (module_id(module), name) in self.bound:
                    continue
                public = name
                if counts[name] > 1 or name in reserved:
                    public = pascal(module.name) + name
                    index = 2
                    while public in originals or public in taken or public in reserved:
                        public = f"{pascal(module.name)}{name}{index}"
                        index += 1
                taken.add(public)
                names[(module_id(module), name)] = public
        return names

    def rename(self, module: Module, annotation: str) -> str:
        def replace(match: re.Match[str]) -> str:
            word = match.group(0)
            if word in BUILTIN_NAMES:
                return word
            key = (module_id(module), word)
            if key in self.bound:
                alias = f"_{pascal(module.name)}{pascal(module.version)}{word}"
                self.imports[
                    f"aioovh._operations.{module.version}.{module.name}.models"
                ].add(f"{word} as {alias}")
                return alias
            public = self.public.get(key)
            if public is not None:
                self.imports[".types"].add(public)
                return public
            return word

        return re.sub(r"[A-Za-z_][A-Za-z0-9_]*", replace, annotation)

    def api_alias(self, call: Call) -> str:
        alias = f"_{call.module.class_name}"
        self.imports[
            f"aioovh._operations.{call.module.version}.{call.module.name}.api"
        ].add(f"{call.module.class_name} as {alias}")
        return alias

    def render_types(self) -> str:
        self.public = self.type_names()
        lines = [GENERATED_MARKER]
        by_module: dict[str, list[str]] = defaultdict(list)
        for module in self.namespace.modules:
            path = f"aioovh._operations.{module.version}.{module.name}.models"
            for (owner, name), public in sorted(self.public.items()):
                if owner == module_id(module):
                    by_module[path].append(
                        name if name == public else f"{name} as {public}"
                    )
        exported = []
        for path, names in sorted(by_module.items()):
            lines.append(f"from {path} import (")
            lines += [f"    {name}," for name in sorted(set(names))]
            lines.append(")")
            exported += [name.split(" as ")[-1] for name in names]
        lines += ["", "__all__ = ["]
        lines += [f"    {name!r}," for name in sorted(set(exported))]
        lines.append("]")
        return "\n".join(lines) + "\n"

    def params(self, call: Call, skip_headers: bool = True) -> list[Param]:
        return [
            p
            for p in call.operation.params
            if p.location != "path" and not (skip_headers and p.wire in CURSOR_HEADERS)
        ]

    def signature(
        self, call: Call, params: list[Param], extra: list[str] | None = None
    ) -> list[str]:
        lines: list[str] = []
        for param in sorted(params, key=lambda p: not p.required):
            annotation = self.rename(call.module, param.annotation)
            if param.required:
                lines.append(f"{param.name}: {annotation}")
            else:
                if not annotation.endswith("| None") and annotation not in (
                    "Any",
                    "None",
                ):
                    annotation += " | None"
                lines.append(f"{param.name}: {annotation} = None")
        return [*(extra or []), *lines]

    def doc(self, call: Call, indent: str = "        ") -> str:
        operation = call.operation
        status = (
            None
            if operation.status == "PRODUCTION"
            else f"API status: {operation.status}."
        )
        return docstring(
            f"{operation.http_method} {operation.path}",
            operation.description,
            status,
            indent=indent,
        ).rstrip("\n")

    def key_access(
        self, resource: Resource | None, call: Call, source: str
    ) -> dict[str, str]:
        """Path parameter of `call` (wire name) to the expression reading it from `source`."""
        segments = path_segments(call.operation)
        params = [
            segment.strip("{}") for segment in segments if segment.startswith("{")
        ]
        key: dict[str, str] = {}
        for wire, alias in call.scope.items():
            if wire in params:
                key[wire] = (
                    f"_scoped({source}, {alias!r}, self._session.client.settings.default_{alias})"
                )
        chain_params = [p for p in params if p not in key]
        names = resource.key_names if resource is not None else []
        for wire, canonical in zip(chain_params, names, strict=False):
            key[wire] = f"_required({source}, {canonical!r})"
        return key

    def call_expression(
        self, call: Call, key: dict[str, str], params: list[Param], cursor: bool = False
    ) -> str:
        api = self.api_alias(call)
        arguments = []
        for param in call.operation.params:
            if param.location == "path" and param.wire in key:
                arguments.append(
                    f"{param.name}={self.convert(call, param, key[param.wire])}"
                )
        for param in params:
            arguments.append(f"{param.name}={param.name}")
        method = call.operation.method_name
        return f"self._session.api({api}).{method}({', '.join(arguments)})"

    def convert(self, call: Call, param: Param, value: str) -> str:
        """A path parameter read from a key (a string), as the type the operation takes."""
        if (
            not value.startswith(("_required(", "_scoped("))
            or param.annotation == "str"
        ):
            return value
        if param.annotation == "int":
            return f"int({value})"
        if param.annotation in ("Instant", "Date"):
            return f"{param.annotation}.parse_iso({value})"
        if param.annotation == "float":
            return f"float({value})"
        return f"{self.rename(call.module, param.annotation)}({value})"

    def uncovered(self, call: Call, key: dict[str, str]) -> list[Param]:
        return [
            p
            for p in call.operation.params
            if p.location == "path" and p.wire not in key
        ]

    def result(
        self, call: Call, expression: str, scope: str, owner: Resource | None = None
    ) -> tuple[str, str]:
        module = call.module
        annotation = call.operation.response
        if annotation == "None":
            return "None", f"        await {expression}"
        bound = self.owned(owner, module, annotation)
        if bound is not None:
            return (
                bound,
                f"        return {bound}._from(self._session, {scope}, await {expression})",
            )
        return self.rename(module, annotation), f"        return await {expression}"

    def owned(self, owner: Resource | None, module: Module, model: str) -> str | None:
        if owner is not None and owner.model == model and owner.module is module:
            return owner.class_name
        resource = self.bound.get((module_id(module), model))
        return None if resource is None else resource.class_name

    def method(
        self, resource: Resource | None, name: str, call: Call, source: str, item: bool
    ) -> list[str]:
        key = self.key_access(resource, call, source)
        scope = call.scope
        scope_names = [] if item else list(dict.fromkeys(scope.values()))
        if not item:
            for wire, alias in scope.items():
                if wire in key:
                    known = (
                        f"{alias} or self._criteria.get({alias!r}) or {source}.get({alias!r})"
                        if resource
                        else alias
                    )
                    default = f"self._session.client.settings.default_{alias}"
                    key[wire] = f"_scoped({{{alias!r}: {known}}}, {alias!r}, {default})"
        params = self.params(call) + self.uncovered(call, key)
        extra = [f"{alias}: str | None = None" for alias in scope_names]
        expression = self.call_expression(call, key, params)
        annotation, statement = self.result(call, expression, source, resource)
        signature = self.signature(call, params, extra)
        out = ["", f"    async def {name}(", "        self,"]
        if signature:
            out.append("        *,")
            out += [f"        {line}," for line in signature]
        out.append(f"    ) -> {annotation}:")
        out.append(self.doc(call))
        out.append(statement)
        return out

    def render_resource(self, resource: Resource) -> list[str]:
        if resource.listing_only:
            return self.render_collection(resource, "", None)
        ref = f"{resource.class_name}Ref"
        loaded = resource.class_name if resource.model else None
        out = [
            "",
            "",
            f"class {ref}(_Ref[{loaded!r}]):"
            if loaded
            else f"class {ref}(_Ref[None]):",
        ]
        out.append(
            f'    """A {singular(resource.name).replace("_", " ")} known by its identifier."""'
        )
        out += ["", f"    _id_name = {resource.param!r}"]
        if resource.load is not None and loaded:
            key = self.key_access(resource, resource.load, "self._key")
            expression = self.call_expression(resource.load, key, [])
            out += ["", f"    async def _load(self) -> {loaded}:"]
            out.append(
                f"        return {loaded}._from(self._session, self._key, await {expression})"
            )
        fields = (
            set(model_fields(resource.module, resource.model))
            if resource.model
            else set()
        )
        members: dict[str, list[str]] = {}
        for name, call in sorted(resource.item_calls.items()):
            members[name] = self.method(resource, name, call, "self._key", item=True)
        for child in resource.children:
            members[child.name] = [
                "",
                "    @property",
                f"    def {child.name}(self) -> {child.class_name}Collection:",
                f"        return {child.class_name}Collection(self._session, self._key)",
            ]
        children = {c.name for c in resource.children}
        for name in sorted(members):
            clash = name in fields or (loaded is not None and name in MODEL_ATTRIBUTES)
            final = (
                name
                if not clash
                else f"{name}_{'items' if name in children else 'call'}"
            )
            out += [
                line.replace(f"def {name}(", f"def {final}(", 1)
                for line in members[name]
            ]
        if loaded and resource.model:
            alias = self.rename(resource.module, resource.model)
            out += ["", "", f"class {loaded}({alias}, {ref}):"]
            out.append(
                f'    """A {singular(resource.name).replace("_", " ")}, loaded."""'
            )
            out += [
                "",
                "    @classmethod",
                f"    def _from(cls, session: _Session, scope: _Key, data: {alias}) -> Self:",
            ]
            out.append("        ref_key: _Key = {**scope}")
            out.append(
                f"        ref_key[{resource.param!r}] = scope.get({resource.param!r}) or {self.id_field(resource)}"
            )
            out.append("        return _bind(cls, session, data, ref_key)")
        out += self.render_collection(resource, ref, loaded)
        return out

    def id_field(self, resource: Resource) -> str:
        assert resource.model is not None
        fields = model_fields(resource.module, resource.model)
        param = snake(resource.param)
        for candidate in (
            param,
            "id",
            "name",
            "service_name",
            param.removesuffix("_id"),
        ):
            if candidate in fields:
                return f"_text(data.{candidate})"
        return "None"

    def render_collection(
        self, resource: Resource, ref: str, loaded: str | None
    ) -> list[str]:
        collection = f"{resource.class_name}Collection"
        item, mode = self.collection_item(resource, loaded)
        out = ["", "", f"class {collection}(_Collection[{item}]):"]
        scope_names = list(dict.fromkeys(resource.scope.values()))
        if resource.listing_only:
            out.append(
                f'    """Every {singular(resource.name).replace("_", " ")}: iterate, or `filter`."""'
            )
        else:
            out.append(
                f'    """Every {singular(resource.name).replace("_", " ")}: iterate, `filter`, or call with an identifier."""'
            )
            id_type = "int | str" if self.integer_id(resource) else "str"
            scoped = "".join(f", {alias}: str | None = None" for alias in scope_names)
            star = ", *" if scoped else ""
            out += [
                "",
                f"    def __call__(self, {snake(resource.param) or 'identifier'}: {id_type}, /{star}{scoped}) -> {ref}:",
            ]
            out.append(
                f"        ref_key: _Key = {{**self._scope, {resource.param!r}: _identifier({snake(resource.param) or 'identifier'})}}"
            )
            for alias in scope_names:
                out.append(
                    f"        ref_key[{alias!r}] = {alias} or self._criteria.get({alias!r}) or self._scope.get({alias!r})"
                )
            out.append(f"        return {ref}._of(self._session, ref_key)")
        if resource.listing is not None:
            listing = resource.listing
            params = self.params(listing)
            extra = [f"{alias}: str | None = None" for alias in scope_names]
            signature = self.signature(listing, params, extra)
            if signature:
                out += ["", "    def filter(", "        self,", "        *,"]
                out += [f"        {line}," for line in signature]
                out.append(f"    ) -> {collection}:")
                out.append(
                    '        """The same collection, narrowed to the items matching these criteria."""'
                )
                names = [p.name for p in params] + scope_names
                out.append(
                    f"        return self._narrowed({', '.join(f'{n}={n}' for n in names)})"
                )
            out += self.items_method(resource, listing, item, mode)
        if resource.create is not None:
            out += self.method(
                resource, "create", resource.create, "self._scope", item=False
            )
        for name, call in sorted(resource.collection_calls.items()):
            out += self.method(resource, name, call, "self._scope", item=False)
        return out

    def collection_item(
        self, resource: Resource, loaded: str | None
    ) -> tuple[str, str]:
        if resource.listing is None:
            return loaded or "Any", "plain"
        response = resource.listing.operation.response
        listed = response[5:-1] if response.startswith("list[") else response
        if loaded and listed == resource.model:
            return loaded, "bind"
        if loaded and resource.load is not None and listed in ("str", "int"):
            return loaded, "load"
        return self.rename(resource.listing.module, listed), "plain"

    def items_method(
        self, resource: Resource, listing: Call, item: str, mode: str
    ) -> list[str]:
        key = self.key_access(resource.parent, listing, "self._scope")
        for wire, alias in resource.scope.items():
            if wire in key:
                key[wire] = (
                    f"_scoped({{**self._scope, **self._criteria}}, {alias!r}, self._session.client.settings.default_{alias})"
                )
        api = self.api_alias(listing)
        arguments = []
        for param in listing.operation.params:
            if param.location == "path":
                value = key.get(param.wire, "None")
                arguments.append(f"{param.name}={self.convert(listing, param, value)}")
        scope_names = set(resource.scope.values())
        arguments.append(
            "**{k: v for k, v in self._criteria.items() if k not in "
            + set_literal(scope_names or {"_"})
            + "}"
        )
        method = listing.operation.method_name
        call_args = ", ".join(arguments)
        out = ["", f"    async def _items(self) -> AsyncIterator[{item}]:"]
        source = (
            f"self._session.api({api}).{method}_iter({call_args})"
            if listing.operation.paginated
            else None
        )
        if mode == "load":
            scope_expr = (
                "{**self._scope, "
                + "".join(
                    f"{a!r}: self._criteria.get({a!r}) or self._scope.get({a!r}), "
                    for a in scope_names
                )
                + "}"
            )
            out.append(
                f"        listed = await self._session.api({api}).{method}({call_args})"
            )
            out.append(f"        scope: _Key = {scope_expr}")
            out.append(
                f"        refs = [{resource.class_name}Ref._of(self._session, {{**scope, {resource.param!r}: str(value)}}) for value in listed]"
            )
            out.append(
                "        async for loaded in _load_each(refs, self._session.client.settings.max_concurrency):"
            )
            out.append("            yield loaded")
            out += ["", "    async def ids(self) -> AsyncIterator[str]:"]
            out.append(
                '        """The identifiers only, without loading the objects."""'
            )
            out.append(
                f"        for value in await self._session.api({api}).{method}({call_args}):"
            )
            out.append("            yield str(value)")
            return out
        convert = (
            f"{item}._from(self._session, self._scope, data)"
            if mode == "bind"
            else "data"
        )
        if source is not None:
            out.append(f"        async for data in {source}:")
        else:
            out.append(
                f"        for data in await self._session.api({api}).{method}({call_args}):"
            )
        out.append(f"            yield {convert}")
        return out

    @staticmethod
    def integer_id(resource: Resource) -> bool:
        for call in [resource.load, *resource.item_calls.values()]:
            if call is None:
                continue
            for param in call.operation.params:
                if param.location == "path" and param.wire == resource.param:
                    return param.annotation == "int"
        return False

    def render_resources(self) -> str:
        body: list[str] = []
        for resource in self.all_resources:
            body += self.render_resource(resource)
        cls = namespace_class_name(self.namespace.name)
        body += ["", "", f"class {cls}(_Namespace):"]
        body.append(f'    """The `{self.namespace.name}` business area."""')
        for root in sorted(self.namespace.roots, key=lambda r: r.name):
            body += [
                "",
                "    @cached_property",
                f"    def {root.name}(self) -> {root.class_name}Collection:",
            ]
            body.append(f"        return {root.class_name}Collection(self._session)")
        if self.namespace.load is not None:
            call = self.namespace.load
            expression = self.call_expression(call, {}, [])
            annotation = self.rename(call.module, call.operation.response)
            body += [
                "",
                f"    def __await__(self) -> Generator[Any, None, {annotation}]:",
            ]
            body.append("        return self._load().__await__()")
            body += ["", f"    async def _load(self) -> {annotation}:"]
            body.append(f"        return await {expression}")
        for name, call in sorted(self.namespace.calls.items()):
            body += self.method(None, name, call, "{}", item=False)
        header = [GENERATED_MARKER, "from __future__ import annotations", ""]
        header += [
            "from collections.abc import AsyncIterator, Generator",
            "from functools import cached_property",
            "from typing import Any, Self",
            "",
        ]
        header.append("from whenever import Date, Instant")
        header.append("")
        header.append(
            "from aioovh._objects import Collection as _Collection, Key as _Key, "
            "Namespace as _Namespace, Ref as _Ref, Session as _Session, bind as _bind, "
            "identifier as _identifier, load_each as _load_each, required as _required, "
            "scoped as _scoped, text as _text"
        )
        for path, names in sorted(self.imports.items()):
            if path == ".types":
                continue
            header.append(f"from {path} import (")
            header += [f"    {name}," for name in sorted(names)]
            header.append(")")
        if self.imports.get(".types"):
            header.append(f"from aioovh.{self.namespace.name}.types import (")
            header += [f"    {name}," for name in sorted(self.imports[".types"])]
            header.append(")")
        return "\n".join(header + body) + "\n"

    def render_init(self) -> str:
        names = [namespace_class_name(self.namespace.name)]
        for resource in self.all_resources:
            names.append(f"{resource.class_name}Collection")
            if not resource.listing_only:
                names.append(f"{resource.class_name}Ref")
                if resource.model:
                    names.append(resource.class_name)
        lines = [
            GENERATED_MARKER,
            f"from aioovh.{self.namespace.name}.resources import (",
        ]
        lines += [f"    {name}," for name in sorted(names)]
        lines += [")", "", "__all__ = ["]
        lines += [f"    {name!r}," for name in sorted(names)]
        lines.append("]")
        return "\n".join(lines) + "\n"


def set_literal(values: Iterable[str]) -> str:
    """A set written in a stable order, so that the generated code never drifts."""
    return "{" + ", ".join(repr(value) for value in sorted(values)) + "}"


def module_id(module: Module) -> str:
    return f"{module.version}.{module.name}"


def namespace_class_name(name: str) -> str:
    return pascal(name) + "Namespace"


def render_namespaces(plan: Plan) -> str:
    lines = [
        GENERATED_MARKER,
        "from functools import cached_property",
        "from typing import TYPE_CHECKING",
        "",
    ]
    lines += ["from aioovh._objects import Session", "", "if TYPE_CHECKING:"]
    for name in sorted(plan.namespaces):
        lines.append(f"    from aioovh.{name} import {namespace_class_name(name)}")
    lines += [
        "",
        "",
        "class Namespaces:",
        '    """Every business area, as an attribute of the client."""',
        "",
        "    _session: Session",
    ]
    for name in sorted(plan.namespaces):
        cls = namespace_class_name(name)
        lines += ["", "    @cached_property", f'    def {name}(self) -> "{cls}":']
        lines.append(
            f"        from aioovh.{name} import {cls}  # lazy: an area is slow to import"
        )
        lines += ["", f"        return {cls}(self._session)"]
    return "\n".join(lines) + "\n"


def render_coverage(plan: Plan) -> str:
    lines = [
        "# Coverage",
        "",
        "Generated by scripts/generate.py: where every operation lives.",
        "",
    ]
    lines += ["| API | Operation | Object layer |", "|---|---|---|"]
    for api, operation, where in sorted(plan.coverage):
        lines.append(f"| {api} | `{operation}` | `{where}` |")
    return "\n".join(lines) + "\n"


def render_tree(plan: Plan) -> str:
    lines = [
        "# Object tree",
        "",
        "Generated by scripts/generate.py from specs/ and mapping.yaml.",
        "",
    ]

    def walk(resource: Resource, depth: int) -> None:
        kind = "listing" if resource.listing_only else f"`{resource.class_name}`"
        members = sorted(
            [*resource.item_calls, *resource.collection_calls]
            + (["create"] if resource.create else [])
        )
        detail = f" ({', '.join(members)})" if members else ""
        lines.append(f"{'  ' * depth}- `{resource.name}`: {kind}{detail}")
        for child in sorted(resource.children, key=lambda r: r.name):
            walk(child, depth + 1)

    for name, namespace in sorted(plan.namespaces.items()):
        lines += [f"## {name}", ""]
        for root in sorted(namespace.roots, key=lambda r: r.name):
            walk(root, 0)
        if namespace.calls:
            lines.append(
                f"- methods: {', '.join(f'`{call}`' for call in sorted(namespace.calls))}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def generate(modules: list[Module]) -> list[str]:
    mapping = yaml.safe_load(MAPPING.read_text(encoding="utf-8"))
    plan = Builder(modules, mapping).build()
    written = []
    for name, namespace in sorted(plan.namespaces.items()):
        renderer = Renderer(plan, namespace, mapping)
        base = PACKAGE / name
        write(base / "types.py", renderer.render_types())
        write(base / "resources.py", renderer.render_resources())
        write(base / "__init__.py", renderer.render_init())
        written.append(str(base))
    write(PACKAGE / "_namespaces.py", render_namespaces(plan))
    write(COVERAGE, render_coverage(plan))
    write(TREE, render_tree(plan))
    return written


def clean() -> None:
    for init in PACKAGE.glob("*/__init__.py"):
        if init.parent.name.startswith("_"):
            continue
        if init.read_text(encoding="utf-8").startswith(GENERATED_MARKER):
            for path in sorted(init.parent.rglob("*"), reverse=True):
                path.unlink() if path.is_file() else path.rmdir()
            init.parent.rmdir()
