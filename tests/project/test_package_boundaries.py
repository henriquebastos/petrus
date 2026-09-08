"""Canonical package imports and architectural import boundaries."""

import ast
import subprocess
import sys

from tests import REPO_ROOT

TEMPORARY_COORDINATION_EXPORTS = {
    "AcceptDelivery",
    "AcceptResult",
    "Action",
    "AdvanceTime",
    "BeginCandidate",
    "Clock",
    "Coordinator",
    "Delivery",
    "DriveOutcome",
    "DrivingPolicy",
    "InFlightView",
    "Runner",
    "Sensor",
    "SimulatedClock",
    "Snapshot",
    "Stop",
    "Wait",
    "choose_conservative",
    "choose_throughput",
}
REMOVED_ROOT_EXPORTS = {
    "Activity",
    "ActivityDeclaration",
    "ActivityExecutionContext",
    "ActivityFailure",
    "ActivityInvocation",
    "ExecutionPolicy",
    "ActivityHandler",
    "Handler",
    "HandlerResult",
    "passthrough",
    "Arc",
    "ArcMode",
    "Binding",
    "Cel",
    "CompletionDeclaration",
    "Delay",
    "Duration",
    "Filter",
    "FilterDeclaration",
    "FilterEvaluationWarning",
    "Guard",
    "GuardDeclaration",
    "GuardEvaluationWarning",
    "Instant",
    "Marking",
    "Net",
    "NetPath",
    "Place",
    "Selection",
    "Token",
    "TokenNotPresent",
    "TokenQueue",
    "Transition",
    "Until",
    "route",
    "ActivityCompleted",
    "ActivityFailed",
    "DeliveryRegistration",
    "DeliveryRegistrationClosed",
    "DeliveryRegistrationOpened",
    "FiringFailed",
    "TimerMatured",
    "entry_instants",
    "replay_marking",
    "decode_record",
    "encode_record",
    "Completion",
    "CompletionEvaluationWarning",
    "FiringOccurrence",
    "FiringOutcome",
    "Instance",
    "NetInstance",
    "PriorAcknowledgement",
    "Scheduler",
    "Status",
    "select_conservative",
}


def test_lazy_root_surface_remains_discoverable_without_optional_imports() -> None:
    code = """
import sys
import petrus
surface = dir(petrus)
removed_coordination = {
    'AcceptDelivery', 'AcceptResult', 'Action', 'AdvanceTime', 'BeginCandidate', 'Clock', 'Coordinator',
    'Delivery', 'DriveOutcome', 'DrivingPolicy', 'InFlightView', 'Runner', 'Sensor', 'SimulatedClock',
    'Snapshot', 'Stop', 'Wait', 'choose_conservative', 'choose_throughput',
}
removed = {'Activity', 'Binding', 'Marking', 'Net', 'Instance', 'NetInstance', 'Status', 'Token'}
assert petrus.__all__ == []
assert removed_coordination.isdisjoint(surface)
assert removed.isdisjoint(surface)
for name in ('EventHistory', 'JsonlEventHistory', 'InMemoryHistoryStore', 'JsonlHistoryStore'):
    assert name not in surface
assert 'psycopg' not in sys.modules
assert 'petrus.motus.dispatch.absurd' not in sys.modules
assert 'petrus.impetus.history_store.postgres' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_implementation_and_maintained_consumers_import_defining_modules_not_project_root() -> None:
    for root in ("src", "tests", "scripts"):
        for path in (REPO_ROOT / root).rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path.relative_to(REPO_ROOT)))
            root_aliases = {
                imported.asname or "petrus"
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for imported in node.names
                if imported.name == "petrus" or (imported.name.startswith("petrus.") and imported.asname is None)
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "petrus":
                    raise AssertionError(f"{path}: import from the defining module, not the empty project namespace")
                if not isinstance(node, ast.Attribute) or node.attr not in REMOVED_ROOT_EXPORTS:
                    continue
                direct_root = isinstance(node.value, ast.Name) and node.value.id in root_aliases
                dynamic_root = (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "__import__"
                    and len(node.value.args) == 1
                    and isinstance(node.value.args[0], ast.Constant)
                    and node.value.args[0].value == "petrus"
                )
                assert not direct_root and not dynamic_root, path


def test_engine_is_canonical_public_and_optional_dependency_safe() -> None:
    code = """
import sys
from petrus.engine import Engine
import petrus
assert not hasattr(petrus, 'Engine')
assert 'petrus.motus.dispatch.absurd' not in sys.modules
assert hasattr(Engine, 'create')
assert hasattr(Engine, 'load')
assert hasattr(Engine, 'wait')
assert not hasattr(Engine, 'queue_for')
assert not any(name == 'psycopg' or name.startswith('psycopg.') for name in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_activity_worker_and_runtime_service_do_not_own_retained_territory_lifecycle() -> None:
    forbidden = {
        "_release_to",
        "begin_release",
        "create",
        "destroy",
        "export",
        "lookup",
        "reclaim",
        "release",
        "retire",
        "settle",
    }
    targets = {
        "src/petrus/agenticus/runtime/codex.py": {"_CodexGondolinActivityAdapter"},
        "src/petrus/agenticus/runtime/_codex_gondolin_service.py": {"_CodexGondolinRuntimeService"},
    }
    for relative, class_names in targets.items():
        tree = ast.parse((REPO_ROOT / relative).read_text(), filename=relative)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name not in class_names:
                continue
            calls = {
                child.func.attr
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
            }
            assert forbidden.isdisjoint(calls), (relative, node.name, forbidden & calls)

    worker = REPO_ROOT / "src/petrus/motus/worker/__init__.py"
    tree = ast.parse(worker.read_text(), filename=str(worker.relative_to(REPO_ROOT)))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module is not None}
    assert "petrus.agenticus.attachment._retention" not in imports


def test_postgres_history_provider_returns_only_the_neutral_engine() -> None:
    from petrus.engine import Engine
    from petrus.engine import postgres

    assert postgres.create_engine.__annotations__["return"] == "Engine"
    assert postgres.load_engine.__annotations__["return"] == "Engine"
    assert not hasattr(postgres, "PostgresEngine")
    assert not hasattr(postgres, "PostgresAuthorityFence")
    assert Engine.__name__ == "Engine"


def test_cv5_demos_host_only_through_public_engine_doors() -> None:
    forbidden_imports = {
        ("petrus.engine._coordination", "Coordinator"),
        ("petrus.engine._postgres", "PostgresAuthorityFence"),
        ("petrus.impetus.history_store.postgres", "PostgresAuthorityFence"),
    }
    forbidden_calls = {"Coordinator", "Instance", "PostgresAuthorityFence"}
    forbidden_motion = {"begin", "candidates"}

    for relative in ("scripts/cv5-fabric-demo.py", "scripts/cv5-lifecycle-demo.py"):
        tree = ast.parse((REPO_ROOT / relative).read_text(), filename=relative)
        imports = {
            (node.module, imported.name)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for imported in node.names
        }
        calls = {
            node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        motion = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        assert not imports & forbidden_imports, relative
        assert not calls & forbidden_calls, relative
        assert not motion & forbidden_motion, relative
        assert ("petrus.engine", "Engine") in imports, relative
        assert ("petrus.engine.postgres", "create_engine") in imports, relative
        assert ("petrus.engine.postgres", "load_engine") in imports, relative


def test_canonical_petrinet_and_binding_facades() -> None:
    from petrus.impetus.binding import ActivityHandler, HandlerResult, passthrough
    from petrus.impetus.binding.cel import compile_completion, compile_filter, compile_guard
    from petrus.impetus.petrinet import Binding, Marking, Net, Token, candidates

    assert all(
        value is not None
        for value in (
            Binding,
            ActivityHandler,
            HandlerResult,
            Marking,
            Net,
            Token,
            candidates,
            passthrough,
            compile_completion,
            compile_filter,
            compile_guard,
        )
    )


def test_canonical_instance_facade_has_no_root_or_deep_compatibility_alias() -> None:
    import importlib.util

    import petrus
    import petrus.impetus.instance as instance_package
    from petrus.impetus.instance import FiringOccurrence, FiringOutcome, Instance
    from petrus.impetus.instance.firing import FiringOccurrence as DeepFiringOccurrence
    from petrus.impetus.instance.firing import FiringOutcome as DeepFiringOutcome

    assert FiringOccurrence is DeepFiringOccurrence
    assert FiringOutcome is DeepFiringOutcome
    assert Instance is instance_package.Instance
    assert not hasattr(petrus, "NetInstance")
    assert not hasattr(instance_package, "NetInstance")
    assert importlib.util.find_spec("impetus") is None


def test_petrinet_import_does_not_load_forbidden_layers() -> None:
    code = """
import sys
import petrus.impetus.petrinet
forbidden = ('petrus.impetus.history', 'petrus.impetus.instance', 'petrus.impetus.binding', 'petrus.motus.worker')
assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules for prefix in forbidden)
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_petrinet_owns_binding_and_history_independent_firing() -> None:
    code = """
import sys
from petrus.impetus.petrinet import Binding, ConsumedTokens, ProducedTokens, ReadTokens, begin_firing, complete_firing
assert all(value is not None for value in (Binding, ConsumedTokens, ProducedTokens, ReadTokens, begin_firing, complete_firing))
forbidden = ('petrus.impetus.history', 'petrus.impetus.instance')
assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules for prefix in forbidden)
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_removed_flat_deep_modules_are_not_speculative_shims() -> None:
    code = """
import importlib.util
assert importlib.util.find_spec('impetus') is None
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_canonical_history_store_facade_does_not_import_optional_postgres_driver() -> None:
    code = """
import sys
import petrus
import petrus.impetus.history as history
import petrus.impetus.history_store as history_store
from petrus.impetus.history_store import DurableAppend, HistoryStore, InMemoryHistoryStore, JsonlHistoryStore, SqliteHistoryStore
from petrus.impetus.history_store.jsonl import JsonlHistoryStore as DeepJsonlHistoryStore
from petrus.impetus.history_store.memory import HistoryStore as DeepHistoryStore
from petrus.impetus.history_store.memory import InMemoryHistoryStore as DeepInMemoryHistoryStore
from petrus.impetus.history_store.sqlite import SqliteHistoryStore as DeepSqliteHistoryStore
assert JsonlHistoryStore is DeepJsonlHistoryStore
assert SqliteHistoryStore is DeepSqliteHistoryStore
assert HistoryStore is DeepHistoryStore
assert InMemoryHistoryStore is DeepInMemoryHistoryStore
assert all(value is not None for value in (DurableAppend, HistoryStore, InMemoryHistoryStore, JsonlHistoryStore, SqliteHistoryStore))
assert not hasattr(petrus, 'EventHistory')
assert not hasattr(petrus, 'JsonlEventHistory')
assert not hasattr(history, 'History')
assert not hasattr(history, 'EventHistory')
for name in ('History', 'EventHistory', 'JsonlEventHistory', 'PostgresEventHistory', 'PostgresHistoryStore'):
    assert not hasattr(history_store, name)
assert not any(name == 'psycopg' or name.startswith('psycopg.') for name in sys.modules)
assert 'petrus.impetus.history_store.postgres' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_postgres_history_store_is_explicit_and_preserves_missing_extra_guidance() -> None:
    code = """
import importlib.abc
import sys
class BlockPsycopg(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'psycopg' or fullname.startswith('psycopg.'):
            raise ModuleNotFoundError("blocked optional dependency")
        return None
sys.meta_path.insert(0, BlockPsycopg())
try:
    import petrus.impetus.history_store.postgres
except ImportError as error:
    message = str(error)
    assert "optional 'postgres' extra" in message
    assert "petrus-runtime[postgres]" in message
else:
    raise AssertionError('PostgreSQL deep import unexpectedly succeeded without psycopg')
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_dispatch_is_canonical_and_coordination_remains_private() -> None:
    import importlib.util

    import petrus
    import petrus.motus.dispatch as dispatch
    import petrus.engine as engine

    assert isinstance(dispatch.InlineDispatch({}), dispatch.Dispatch)
    assert isinstance(dispatch.InMemoryDispatch(), dispatch.Dispatch)
    assert dispatch.LocalDispatch.__module__ == "petrus.motus.dispatch.local"
    assert dispatch.ActivityAttempt.__module__ == "petrus.motus.dispatch"
    for removed in (
        "ExecutionAdapter",
        "ExecutionRuntime",
        "InlineAdapter",
        "InlineDispatcher",
        "PendingPoolAdapter",
    ):
        assert not hasattr(petrus, removed)
        assert removed not in dir(petrus)
        assert not hasattr(dispatch, removed)
    assert petrus.__all__ == []
    for name in TEMPORARY_COORDINATION_EXPORTS:
        assert not hasattr(petrus, name)
    assert not hasattr(engine, "Runner")
    assert importlib.util.find_spec("impetus") is None
    assert importlib.util.find_spec("petrus._coordination") is None
    assert importlib.util.find_spec("petrus.engine._coordination") is not None
    assert "Coordinator" not in engine.__all__
    assert set(engine.__all__) == {
        "AcceptedDelivery",
        "AcceptDelivery",
        "AcceptResult",
        "Action",
        "AdvanceTime",
        "BeginCandidate",
        "Clock",
        "Delivery",
        "DriveOutcome",
        "DrivingPolicy",
        "Engine",
        "InFlightView",
        "Sensor",
        "SimulatedClock",
        "Snapshot",
        "Stop",
        "Wait",
        "choose_conservative",
        "choose_throughput",
    }
    assert "authority" not in dir(petrus)


def test_dispatch_import_is_optional_dependency_safe_and_absurd_is_canonical() -> None:
    code = """
import importlib.util
import sys
import petrus.motus.dispatch
assert importlib.util.find_spec('petrus.motus.dispatch.absurd') is not None
assert importlib.util.find_spec('impetus') is None
assert 'petrus.motus.dispatch.absurd' not in sys.modules
assert 'petrus.motus.transport.zeromq' not in sys.modules
assert 'zmq' not in sys.modules
assert not any(name == 'psycopg' or name.startswith('psycopg.') for name in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_absurd_dispatch_removed_name_has_no_deep_compatibility_alias() -> None:
    from petrus.motus.dispatch import absurd
    from petrus.engine import Engine
    from petrus.engine import absurd as absurd_engine

    assert not hasattr(absurd, "AbsurdExecutionAdapter")
    assert not hasattr(absurd, "AbsurdEngine")
    assert absurd_engine.create_engine.__annotations__["return"] == "Engine"
    assert absurd_engine.load_engine.__annotations__["return"] == "Engine"
    assert Engine.__name__ == "Engine"


def test_absurd_deep_import_preserves_missing_extra_guidance() -> None:
    code = """
import importlib.abc
import sys
class BlockAbsurdExtra(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'psycopg' or fullname.startswith('psycopg.'):
            raise ModuleNotFoundError('blocked optional dependency')
        return None
sys.meta_path.insert(0, BlockAbsurdExtra())
try:
    import petrus.motus.dispatch.absurd
except ImportError as error:
    message = str(error)
    assert "optional 'absurd' extra" in message
    assert 'petrus-runtime[absurd]' in message
else:
    raise AssertionError('Absurd deep import unexpectedly succeeded without psycopg')
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_worker_import_does_not_require_absurd_extra() -> None:
    code = """
import importlib.abc
import sys
class BlockAbsurdExtra(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'absurd_sdk' or fullname.startswith('absurd_sdk.') or fullname == 'zmq' or fullname.startswith('zmq.'):
            raise ModuleNotFoundError('blocked optional dependency')
        return None
sys.meta_path.insert(0, BlockAbsurdExtra())
import petrus.motus.worker
assert 'absurd_sdk' not in sys.modules
assert 'petrus.motus.dispatch.absurd' not in sys.modules
assert 'zmq' not in sys.modules
assert 'petrus.motus.transport.zeromq' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_worker_package_public_contract_and_module_cli() -> None:
    code = """
from petrus.motus.worker import Worker
from petrus.motus.worker._cli import main
assert all(value is not None for value in (Worker, main))
"""
    subprocess.run([sys.executable, "-c", code], check=True)
    result = subprocess.run([sys.executable, "-m", "petrus.motus.worker", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.startswith("usage: python -m petrus.motus.worker")
    assert "--queue" in result.stdout
    assert "zeromq" in result.stdout
    assert "--capability" not in result.stdout


def test_zeromq_transport_base_import_is_optional_and_deep_import_has_guidance() -> None:
    code = """
import importlib.abc
import sys
class BlockZeroMQExtra(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'zmq' or fullname.startswith('zmq.'):
            raise ModuleNotFoundError('blocked optional dependency')
        return None
sys.meta_path.insert(0, BlockZeroMQExtra())
import petrus.motus.transport
assert 'zmq' not in sys.modules
try:
    import petrus.motus.transport.zeromq
except ImportError as error:
    message = str(error)
    assert "optional 'zeromq' extra" in message
    assert 'petrus-runtime[zeromq]' in message
else:
    raise AssertionError('ZeroMQ deep import unexpectedly succeeded without pyzmq')
"""
    subprocess.run([sys.executable, "-c", code], check=True)
