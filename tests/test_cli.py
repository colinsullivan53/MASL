import subprocess
import sys

def test_dry_run_basic(tmp_path):
    masl_file = tmp_path / "test.masl"
    masl_file.write_text("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } Stocks 4 Time 8 }
        Static test { P1 button(A) :: wait 5 }
    }
    """)
    result = subprocess.run(
        [sys.executable, "-m", "src", str(masl_file), "--dry-run", "--frames", "10"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "Frame" in result.stdout

def test_dry_run_debug(tmp_path):
    masl_file = tmp_path / "test.masl"
    masl_file.write_text("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } Stocks 4 Time 8 }
        Static test { P1 button(A) :: wait 3 }
    }
    """)
    result = subprocess.run(
        [sys.executable, "-m", "src", str(masl_file), "--dry-run", "--frames", "5", "--debug"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    # Debug shows all frames including neutral
    assert "neutral" in result.stdout

def test_missing_file():
    result = subprocess.run(
        [sys.executable, "-m", "src", "nonexistent.masl", "--dry-run"],
        capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "not found" in result.stderr.lower()

def test_no_dolphin_no_iso(tmp_path):
    masl_file = tmp_path / "test.masl"
    masl_file.write_text("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } Stocks 4 Time 8 }
        Static test { P1 button(A) }
    }
    """)
    result = subprocess.run(
        [sys.executable, "-m", "src", str(masl_file)],
        capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "dolphin" in result.stderr.lower() or "iso" in result.stderr.lower()

def test_syntax_error(tmp_path):
    masl_file = tmp_path / "bad.masl"
    masl_file.write_text("Match { invalid syntax @@ }")
    result = subprocess.run(
        [sys.executable, "-m", "src", str(masl_file), "--dry-run"],
        capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "Error" in result.stderr or "error" in result.stderr
