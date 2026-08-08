"""SQLite Engine ownership, fencing, and resource behavior."""

import multiprocessing
import warnings

import pytest

from petrus.engine.sqlite import create_engine, load_engine
from petrus.impetus.petrinet import Net
from petrus.motus.dispatch import InlineDispatch


def _empty_net() -> Net:
    return Net(places=[], transitions=[], arcs=[])


def _hold_engine(path, instance, ready, release):
    engine = create_engine(path, _empty_net(), instance, dispatch=InlineDispatch({}))
    ready.put("ready")
    release.wait(10)
    engine.close()


def _try_load(path, instance, result):
    try:
        engine = load_engine(path, _empty_net(), instance, dispatch=InlineDispatch({}))
    except BaseException as error:
        result.put((type(error).__name__, str(error)))
    else:
        engine.close()
        result.put(("opened", ""))


def test_fenced_engine_refuses_same_database_and_instance_then_releases(tmp_path):
    path = tmp_path / "history.sqlite3"
    first = create_engine(path, _empty_net(), "one", dispatch=InlineDispatch({}))
    with pytest.raises(RuntimeError, match="second canonical writer"):
        load_engine(path, _empty_net(), "one", dispatch=InlineDispatch({}))
    first.close()
    resumed = load_engine(path, _empty_net(), "one", dispatch=InlineDispatch({}))
    resumed.close()
    assert next((path.parent / ".impetus-sqlite-locks").iterdir()).is_file()


def test_fenced_engines_scope_authority_by_database_and_instance(tmp_path):
    one = create_engine(tmp_path / "shared.sqlite3", _empty_net(), "one", dispatch=InlineDispatch({}))
    two = create_engine(tmp_path / "shared.sqlite3", _empty_net(), "two", dispatch=InlineDispatch({}))
    other = create_engine(tmp_path / "other.sqlite3", _empty_net(), "one", dispatch=InlineDispatch({}))
    for engine in (one, two, other):
        engine.close()


def test_writing_door_poison_releases_sqlite_resources(tmp_path):
    path = tmp_path / "history.sqlite3"
    engine = create_engine(path, _empty_net(), "one", dispatch=InlineDispatch({}))
    with pytest.raises(ValueError):
        engine.seal("missing")
    resumed = load_engine(path, _empty_net(), "one", dispatch=InlineDispatch({}))
    resumed.close()
    engine.close()


def test_spawned_process_contention_and_holder_death_release(tmp_path):
    context = multiprocessing.get_context("spawn")
    path = tmp_path / "history.sqlite3"
    ready, release = context.Queue(), context.Event()
    holder = context.Process(target=_hold_engine, args=(path, "one", ready, release))
    holder.start()
    assert ready.get(timeout=10) == "ready"
    result = context.Queue()
    contender = context.Process(target=_try_load, args=(path, "one", result))
    contender.start()
    contender.join(10)
    assert not contender.is_alive()
    assert result.get(timeout=1)[0:1] == ("RuntimeError",)
    holder.terminate()
    holder.join(10)
    reopened = load_engine(path, _empty_net(), "one", dispatch=InlineDispatch({}))
    reopened.close()


@pytest.mark.skipif("fork" not in multiprocessing.get_all_start_methods(), reason="requires POSIX fork")
def test_forked_engine_refuses_and_child_does_not_retain_fence(tmp_path):
    context = multiprocessing.get_context("fork")
    path = tmp_path / "history.sqlite3"
    engine = create_engine(path, _empty_net(), "one", dispatch=InlineDispatch({}))
    child_ready, child_exit = context.Pipe(duplex=True)

    def inherited_child():
        try:
            engine.status
        except BaseException as error:
            child_ready.send((type(error).__name__, str(error)))
        child_ready.recv()

    child = context.Process(target=inherited_child)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"This process .* is multi-threaded, use of fork\(\) may lead to deadlocks in the child\.",
            category=DeprecationWarning,
        )
        child.start()
    kind, message = child_exit.recv()
    assert kind == "RuntimeError" and "inherited across fork" in message
    engine.close()
    reopened = load_engine(path, _empty_net(), "one", dispatch=InlineDispatch({}))
    reopened.close()
    child_exit.send("exit")
    child.join(10)
    assert not child.is_alive()
