"""Compatibility shims for old Bugs4Q Qiskit snippets.

The benchmark includes many standalone scripts written for pre-1.0 Qiskit.  This
module installs a small, deterministic shim layer for APIs that have direct
Terra/Aer 0.45 equivalents.  Larger framework dependencies such as Aqua, Ignis,
and Nature are intentionally not emulated here; manifest generation records those
as explicit exclusions.
"""
from __future__ import annotations

import sys
import types
from typing import Any


_INSTALLED = False


def install_qiskit_compat() -> None:
    """Install idempotent import and method aliases used by legacy subjects."""
    global _INSTALLED
    if _INSTALLED:
        return

    import qiskit
    from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
    from qiskit_aer import Aer, AerSimulator, QasmSimulator, StatevectorSimulator

    qiskit.Aer = Aer
    qiskit.BasicAer = Aer
    qiskit.execute = execute
    qiskit.compile = compile
    qiskit.QuantumProgram = QuantumProgram
    qiskit.QuantumRegister = QuantumRegister
    qiskit.ClassicalRegister = ClassicalRegister
    qiskit.QuantumCircuit = QuantumCircuit
    qiskit.IBMQ = _IBMQShim(Aer)

    _install_gate_aliases(QuantumCircuit)
    _install_old_controlled_gate_kwargs(QuantumCircuit)
    _install_transpiler_aliases()
    _install_module_aliases(qiskit, Aer, AerSimulator, QasmSimulator, StatevectorSimulator)

    _INSTALLED = True


def execute(circuits: Any, backend: Any = None, **kwargs: Any):
    """Small replacement for removed ``qiskit.execute``.

    It preserves the common Bugs4Q usage pattern: build/run one circuit or a list
    of circuits on an Aer-like backend and return the backend job.
    """
    from qiskit_aer import Aer

    if backend is None:
        backend = Aer.get_backend("qasm_simulator")
    elif isinstance(backend, str):
        backend = Aer.get_backend(_backend_alias(backend))

    run_kwargs = dict(kwargs)
    run_kwargs.pop("backend_options", None)
    run_kwargs.pop("compile_config", None)
    run_kwargs.pop("config", None)
    run_kwargs.pop("qobj_id", None)
    run_kwargs.pop("qobj_header", None)
    run_kwargs.pop("max_credits", None)
    run_kwargs.pop("timeout", None)
    run_kwargs.pop("initial_layout", None)
    if "shot" in run_kwargs and "shots" not in run_kwargs:
        run_kwargs["shots"] = run_kwargs.pop("shot")
    if "shots" in run_kwargs:
        run_kwargs["shots"] = min(int(run_kwargs["shots"]), 1024)
    return backend.run(circuits, **run_kwargs)


def compile(circuits: Any, backend: Any = None, **kwargs: Any):
    """Small replacement for removed ``qiskit.compile``.

    Old Bugs4Q snippets commonly pass the returned object straight to
    ``backend.run``. Returning a transpiled circuit/list is the closest direct
    Terra 0.45 equivalent for these deterministic extraction runs.
    """
    from qiskit import transpile
    from qiskit_aer import Aer

    if isinstance(backend, str):
        backend = Aer.get_backend(_backend_alias(backend))
    safe_kwargs = dict(kwargs)
    safe_kwargs.pop("noise_model", None)
    safe_kwargs.pop("shots", None)
    safe_kwargs.pop("max_credits", None)
    safe_kwargs.pop("timeout", None)
    try:
        return transpile(circuits, backend=backend, **safe_kwargs)
    except Exception:
        return circuits


def available_backends(*_args: Any, **_kwargs: Any) -> list[str]:
    return ["qasm_simulator", "statevector_simulator", "aer_simulator"]


def get_backend(name: str = "qasm_simulator", *_args: Any, **_kwargs: Any):
    from qiskit_aer import Aer
    return Aer.get_backend(_backend_alias(name))


def _backend_alias(name: str) -> str:
    aliases = {
        "local_qasm_simulator": "qasm_simulator",
        "local_qasm_simulator_cpp": "qasm_simulator",
        "local_statevector_simulator": "statevector_simulator",
        "qasm_simulator_py": "qasm_simulator",
        "ibmq_qasm_simulator": "qasm_simulator",
        "ibmqx5": "qasm_simulator",
        "ibmq_16_melbourne": "qasm_simulator",
        "ibmq_16_rueschlikon": "qasm_simulator",
    }
    return aliases.get(name, name)


class QuantumProgram:
    """Minimal pre-0.6 ``QuantumProgram`` shim used by Bugs4Q scripts."""

    def __init__(self):
        self._circuits: dict[str, Any] = {}

    def set_api(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def create_quantum_register(self, name: str, size: int):
        from qiskit import QuantumRegister
        return QuantumRegister(size, name)

    def create_classical_register(self, name: str, size: int):
        from qiskit import ClassicalRegister
        return ClassicalRegister(size, name)

    def create_circuit(self, name: str, qregs: list[Any], cregs: list[Any]):
        from qiskit import QuantumCircuit
        qc = QuantumCircuit(*(list(qregs) + list(cregs)), name=name)
        self._circuits[name] = qc
        return qc

    def execute(self, circuits: Any, backend: Any = None, **kwargs: Any):
        if isinstance(circuits, str):
            circuits = self._circuits[circuits]
        elif isinstance(circuits, list):
            circuits = [self._circuits.get(c, c) for c in circuits]
        return execute(circuits, backend=backend, **kwargs).result()


class _IBMQShim:
    def __init__(self, aer):
        self._aer = aer

    def load_accounts(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def load_account(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def get_backend(self, name: str, *_args: Any, **_kwargs: Any):
        return self._aer.get_backend(_backend_alias(name))


def _install_gate_aliases(cls) -> None:
    if not hasattr(cls, "u1"):
        cls.u1 = lambda self, lam, qubit: self.p(lam, qubit)
    if not hasattr(cls, "u2"):
        cls.u2 = lambda self, phi, lam, qubit: self.u(1.5707963267948966, phi, lam, qubit)
    if not hasattr(cls, "u3"):
        cls.u3 = lambda self, theta, phi, lam, qubit: self.u(theta, phi, lam, qubit)
    if not hasattr(cls, "cu1"):
        cls.cu1 = lambda self, lam, control, target: self.cp(lam, control, target)
    if not hasattr(cls, "iden"):
        cls.iden = lambda self, qubit: self.id(qubit)
    if not hasattr(cls, "__add__"):
        cls.__add__ = lambda self, other: self.compose(other, inplace=False)


def _install_old_controlled_gate_kwargs(cls) -> None:
    """Accept legacy label/ctrl_state kwargs on cx/ccx when directly expressible."""
    from qiskit.circuit.library import XGate

    if not hasattr(cls, "_qmtester_orig_cx"):
        cls._qmtester_orig_cx = cls.cx

        def cx(self, control, target, *args, **kwargs):
            kwargs.pop("label", None)
            ctrl_state = kwargs.pop("ctrl_state", None)
            if ctrl_state is None:
                return cls._qmtester_orig_cx(self, control, target, *args, **kwargs)
            gate = XGate().control(1, ctrl_state=str(ctrl_state))
            return self.append(gate, [control, target], [])

        cls.cx = cx

    if not hasattr(cls, "_qmtester_orig_ccx"):
        cls._qmtester_orig_ccx = cls.ccx

        def ccx(self, control1, control2, target, *args, **kwargs):
            kwargs.pop("label", None)
            ctrl_state = kwargs.pop("ctrl_state", None)
            if ctrl_state is None:
                return cls._qmtester_orig_ccx(self, control1, control2, target, *args, **kwargs)
            gate = XGate().control(2, ctrl_state=str(ctrl_state))
            return self.append(gate, [control1, control2, target], [])

        cls.ccx = ccx


def _install_transpiler_aliases() -> None:
    try:
        from qiskit.transpiler import PassManager
        if not hasattr(PassManager, "run_passes"):
            PassManager.run_passes = lambda self, circuit: self.run(circuit)
    except Exception:
        pass


def _install_module_aliases(qiskit, Aer, AerSimulator, QasmSimulator, StatevectorSimulator) -> None:
    aer_mod = types.ModuleType("qiskit.providers.aer")
    aer_mod.Aer = Aer
    aer_mod.AerSimulator = AerSimulator
    aer_mod.QasmSimulator = QasmSimulator
    aer_mod.StatevectorSimulator = StatevectorSimulator
    aer_mod.__dict__.update({
        "Aer": Aer,
        "AerSimulator": AerSimulator,
        "QasmSimulator": QasmSimulator,
        "StatevectorSimulator": StatevectorSimulator,
    })
    sys.modules.setdefault("qiskit.providers.aer", aer_mod)

    aer_backends_mod = types.ModuleType("qiskit.providers.aer.backends")
    aer_backends_mod.QasmSimulator = QasmSimulator
    aer_backends_mod.StatevectorSimulator = StatevectorSimulator
    aer_backends_mod.AerSimulator = AerSimulator
    sys.modules.setdefault("qiskit.providers.aer.backends", aer_backends_mod)

    try:
        import qiskit_aer.noise as aer_noise
        sys.modules.setdefault("qiskit.providers.aer.noise", aer_noise)
    except Exception:
        pass

    wrapper_mod = types.ModuleType("qiskit.wrapper")
    wrapper_mod.execute = execute
    wrapper_mod.available_backends = available_backends
    wrapper_mod.get_backend = get_backend
    sys.modules.setdefault("qiskit.wrapper", wrapper_mod)

    execute_function_mod = types.ModuleType("qiskit.execute_function")
    execute_function_mod.execute = execute
    sys.modules.setdefault("qiskit.execute_function", execute_function_mod)

    qconfig_mod = types.ModuleType("Qconfig")
    qconfig_mod.APItoken = ""
    qconfig_mod.config = {"url": ""}
    sys.modules.setdefault("Qconfig", qconfig_mod)

    try:
        import qiskit.circuit.measure as measure_mod
        sys.modules.setdefault("qiskit.circuit.measure", measure_mod)
    except Exception:
        pass

    try:
        import qiskit.circuit.library as library
        standard_mod = types.ModuleType("qiskit.extensions.standard")
        for name in dir(library):
            if not name.startswith("_"):
                setattr(standard_mod, name, getattr(library, name))
        sys.modules.setdefault("qiskit.extensions.standard", standard_mod)
    except Exception:
        pass

    try:
        import qiskit.visualization as visualization
        sys.modules.setdefault("qiskit.tools.visualization", visualization)
    except Exception:
        pass

    try:
        import qiskit.providers.jobstatus as jobstatus
        backends_mod = types.ModuleType("qiskit.backends")
        sys.modules.setdefault("qiskit.backends", backends_mod)
        sys.modules.setdefault("qiskit.backends.jobstatus", jobstatus)
    except Exception:
        pass

    simulator_mod = sys.modules.get("qiskit.extensions.simulator")
    if simulator_mod is None:
        simulator_mod = types.ModuleType("qiskit.extensions.simulator")
        sys.modules["qiskit.extensions.simulator"] = simulator_mod
    simulator_mod.wait = lambda *args, **kwargs: None

    try:
        from qiskit.providers import fake_provider
        mock_almaden = types.ModuleType("qiskit.test.mock.backends.almaden")
        fake_cls = getattr(fake_provider, "FakeAlmaden", None)
        if fake_cls is not None:
            mock_almaden.FakeAlmaden = fake_cls
        sys.modules.setdefault("qiskit.test", types.ModuleType("qiskit.test"))
        sys.modules.setdefault("qiskit.test.mock", types.ModuleType("qiskit.test.mock"))
        sys.modules.setdefault("qiskit.test.mock.backends", types.ModuleType("qiskit.test.mock.backends"))
        sys.modules.setdefault("qiskit.test.mock.backends.almaden", mock_almaden)
    except Exception:
        pass
