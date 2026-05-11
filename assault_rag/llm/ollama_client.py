import subprocess
import re

# Regex para eliminar secuencias ANSI (códigos de terminal)
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    """
    return ANSI_ESCAPE_RE.sub("", text)


def call_llm(prompt: str) -> str:
    """
    Call the local LLM (Ollama) and return clean text output.
    """

    proc = subprocess.run(
        ["ollama", "run", "llama3:8b"],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8"))

    raw_output = proc.stdout.decode("utf-8")
    clean_output = strip_ansi(raw_output)

    return clean_output.strip()