import importlib.util
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.services.step1_rates.activator_mappers import _resolve_port


def _load_seed():
    # scripts/ 不是 python 包，动态加载(同 admin.py 套路)
    p = Path(__file__).resolve().parents[4] / "scripts" / "seed_data.py"
    spec = importlib.util.spec_from_file_location("seed_data", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_new_ports_seeded_and_resolvable():
    import app.models  # noqa: F401
    mod = _load_seed()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    mod.seed_ports(s)
    for nm in ["Cochin", "Colombo", "Kolkata", "Mangalore", "Pipavav",
               "Naha", "Shekou", "Hilo", "Philadelphia", "Durban"]:
        assert _resolve_port(s, nm) is not None, f"{nm} 应在补充后可解析"
    s.close()
    engine.dispose()
