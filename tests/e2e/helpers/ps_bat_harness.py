from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

_STUB_CS_SOURCE = r"""
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

public class Sh3dTestStub {
    static string Esc(string s) {
        if (s == null) return "null";
        var sb = new StringBuilder("\"");
        foreach (char c in s) {
            if (c == '\\') sb.Append("\\\\");
            else if (c == '"') sb.Append("\\\"");
            else if (c == '\n') sb.Append("\\n");
            else if (c == '\r') sb.Append("\\r");
            else if (c == '\t') sb.Append("\\t");
            else if (c < 32) sb.AppendFormat("\\u{0:x4}", (int)c);
            else sb.Append(c);
        }
        sb.Append("\"");
        return sb.ToString();
    }

    static string GetEnvOrNull(string name) {
        return Environment.GetEnvironmentVariable(name);
    }

    static void CopySelf(string dest) {
        string self = Process.GetCurrentProcess().MainModule.FileName;
        string dir = Path.GetDirectoryName(dest);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        File.Copy(self, dest, true);
    }

    static string GetScStateFile(string serviceName) {
        string stateDir = Environment.GetEnvironmentVariable("SH3D_SC_STATE_DIR");
        if (string.IsNullOrEmpty(stateDir)) return null;
        Directory.CreateDirectory(stateDir);
        return Path.Combine(stateDir, serviceName + ".state");
    }

    static string ReadServiceState(string serviceName) {
        string f = GetScStateFile(serviceName);
        if (!string.IsNullOrEmpty(f) && File.Exists(f)) {
            return File.ReadAllText(f, new UTF8Encoding(false)).Trim();
        }
        string mode = Environment.GetEnvironmentVariable("SH3D_NSSM_STATUS_EXIT") ?? "1";
        if (mode == "0") return "RUNNING";
        if (mode == "3") return "STOPPED";
        return "ABSENT";
    }

    static void WriteServiceState(string serviceName, string state) {
        string f = GetScStateFile(serviceName);
        if (!string.IsNullOrEmpty(f)) {
            File.WriteAllText(f, state, new UTF8Encoding(false));
        }
    }

    public static int Main(string[] args) {
        string selfPath = Process.GetCurrentProcess().MainModule.FileName;
        string exeName = Path.GetFileName(selfPath).ToLowerInvariant();
        string logPath = Environment.GetEnvironmentVariable("SH3D_STUB_LOG");

        if (!string.IsNullOrEmpty(logPath)) {
            var argList = new List<string>();
            foreach (string a in args) argList.Add(Esc(a));
            string[] envKeys = new[] {
                "SPATIAL_SERVER_HOST", "SPATIAL_SERVER_PORT",
                "REOLINK_CARRAIO_PASS", "REOLINK_CARRAIO_PASSWORD",
                "MQTT_PASS", "MQTT_PASSWORD",
                "GO2RTC_CANDIDATE_LAN", "GO2RTC_CANDIDATE_TAILSCALE",
                "SPATIAL_AUTH_REQUIRED", "SPATIAL_SESSION_SECRET"
            };
            var envEntries = new List<string>();
            foreach (string k in envKeys) {
                envEntries.Add(Esc(k) + ":" + Esc(GetEnvOrNull(k)));
            }
            string jsonLine = "{"
                + "\"exe\":" + Esc(exeName) + ","
                + "\"full_path\":" + Esc(selfPath) + ","
                + "\"cwd\":" + Esc(Environment.CurrentDirectory) + ","
                + "\"args\":[" + string.Join(",", argList.ToArray()) + "],"
                + "\"env\":{" + string.Join(",", envEntries.ToArray()) + "}"
                + "}\n";

            for (int attempt = 0; attempt < 25; attempt++) {
                try {
                    string logDir = Path.GetDirectoryName(logPath);
                    if (!string.IsNullOrEmpty(logDir)) Directory.CreateDirectory(logDir);
                    using (var fs = new FileStream(logPath, FileMode.Append, FileAccess.Write, FileShare.ReadWrite))
                    using (var sw = new StreamWriter(fs, new UTF8Encoding(false))) {
                        sw.Write(jsonLine);
                    }
                    break;
                } catch (IOException) {
                    Thread.Sleep(25);
                }
            }
        }

        // Simulate `python -m venv <dir>`
        if (exeName == "python.exe" && args.Length >= 3 && args[0] == "-m" && args[1] == "venv") {
            string venvDir = args[2];
            CopySelf(Path.Combine(venvDir, "Scripts", "python.exe"));
            CopySelf(Path.Combine(venvDir, "Scripts", "uvicorn.exe"));
            return 0;
        }

        // Simulate `sc.exe query <service>`
        if (exeName == "sc.exe" && args.Length >= 2 && args[0].ToLowerInvariant() == "query") {
            string svc = args[1];
            string st = ReadServiceState(svc);
            if (st == "ABSENT") {
                Console.Error.WriteLine("[SC] EnumQueryServicesStatus:OpenService FAILED 1060");
                return 1060;
            }
            if (st == "RUNNING") {
                Console.WriteLine("        STATE              : 4  RUNNING");
                return 0;
            }
            Console.WriteLine("        STATE              : 1  STOPPED");
            return 0;
        }

        // Simulate `nssm.exe` stateful commands
        if (exeName == "nssm.exe" && args.Length >= 2) {
            string sub = args[0].ToLowerInvariant();
            string svc = args[1];
            if (sub == "status") {
                string st = ReadServiceState(svc);
                if (st == "RUNNING") { Console.WriteLine("SERVICE_RUNNING"); return 0; }
                if (st == "STOPPED") { Console.WriteLine("SERVICE_STOPPED"); return 3; }
                Console.Error.WriteLine("Can't open service!");
                return 1;
            }
            if (sub == "install") {
                WriteServiceState(svc, "STOPPED");
                return 0;
            }
            if (sub == "start") {
                WriteServiceState(svc, "RUNNING");
                return 0;
            }
            if (sub == "stop") {
                WriteServiceState(svc, "STOPPED");
                return 0;
            }
            if (sub == "restart") {
                WriteServiceState(svc, "RUNNING");
                return 0;
            }
        }

        // Simulate `git.exe` for update_services.bat without MSYS/network dependencies
        if (exeName == "git.exe" && args.Length >= 1) {
            string sub = args[0].ToLowerInvariant();
            string stateDir = Environment.GetEnvironmentVariable("SH3D_SC_STATE_DIR") ?? Path.GetTempPath();
            string headFile = Path.Combine(stateDir, "git_reset_done.flag");
            string oldHead = Environment.GetEnvironmentVariable("SH3D_GIT_OLD_HEAD") ?? "1111111111111111111111111111111111111111";
            string newHead = Environment.GetEnvironmentVariable("SH3D_GIT_NEW_HEAD") ?? oldHead;

            if (sub == "rev-parse" && args.Length >= 2 && args[1] == "HEAD") {
                Console.WriteLine(File.Exists(headFile) ? newHead : oldHead);
                return 0;
            }
            if (sub == "fetch") {
                if (Environment.GetEnvironmentVariable("SH3D_GIT_FETCH_FAIL") == "1") {
                    Console.Error.WriteLine("fatal: unable to access origin");
                    return 128;
                }
                return 0;
            }
            if (sub == "checkout" || sub == "reset") {
                Directory.CreateDirectory(stateDir);
                File.WriteAllText(headFile, "1", new UTF8Encoding(false));
                return 0;
            }
            if (sub == "diff") {
                string changedRaw = Environment.GetEnvironmentVariable("SH3D_GIT_CHANGED_FILES") ?? "";
                if (string.IsNullOrEmpty(changedRaw)) return 0;
                int dashDash = Array.IndexOf(args, "--");
                if (dashDash < 0 || dashDash == args.Length - 1) return 1;
                string[] changed = changedRaw.Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                for (int i = dashDash + 1; i < args.Length; i++) {
                    string watched = args[i].Replace('\\', '/').TrimEnd('/');
                    foreach (string ch in changed) {
                        string c = ch.Trim().Replace('\\', '/');
                        if (c == watched || c.StartsWith(watched + "/")) return 1;
                    }
                }
                return 0;
            }
            return 0;
        }

        // Simulate `net.exe` (e.g. `net session`, `net start`, `net stop`)
        if (exeName == "net.exe" && args.Length >= 1) {
            string sub = args[0].ToLowerInvariant();
            if (sub == "session") return 1; // Non-admin in dry-run
            if (sub == "start" && args.Length >= 2) { WriteServiceState(args[1], "RUNNING"); return 0; }
            if (sub == "stop" && args.Length >= 2) { WriteServiceState(args[1], "STOPPED"); return 0; }
        }

        // Simulate `where.exe`
        if (exeName == "where.exe" && args.Length > 0) {
            string failWhere = Environment.GetEnvironmentVariable("SH3D_WHERE_FAIL");
            if (!string.IsNullOrEmpty(failWhere) && string.Equals(failWhere, args[0], StringComparison.OrdinalIgnoreCase)) {
                return 1;
            }
            Console.WriteLine(args[0]);
            return 0;
        }

        string failExe = Environment.GetEnvironmentVariable("SH3D_STUB_FAIL_EXE");
        if (!string.IsNullOrEmpty(failExe) && string.Equals(failExe, exeName, StringComparison.OrdinalIgnoreCase)) {
            return 1;
        }

        return 0;
    }
}
"""

_CACHED_STUB_EXE: Optional[Path] = None
_CACHED_LARGE_STUB_EXE: Optional[Path] = None


def get_stub_exe(*, min_bytes: int = 0) -> Path:
    """Compile (once per process) a harmless native Windows PE stub executable."""
    global _CACHED_STUB_EXE, _CACHED_LARGE_STUB_EXE
    if min_bytes > 0 and _CACHED_LARGE_STUB_EXE is not None and _CACHED_LARGE_STUB_EXE.exists():
        return _CACHED_LARGE_STUB_EXE
    if min_bytes == 0 and _CACHED_STUB_EXE is not None and _CACHED_STUB_EXE.exists():
        return _CACHED_STUB_EXE

    cache_dir = Path(tempfile.gettempdir()) / "sh3d_e2e_stub_cache_v2"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stub_exe = cache_dir / "sh3d_stub.exe"
    stub_cs = cache_dir / "sh3d_stub.cs"

    if not stub_exe.exists() or stub_cs.read_text(encoding="utf-8") != _STUB_CS_SOURCE if stub_cs.exists() else True:
        stub_cs.write_text(_STUB_CS_SOURCE, encoding="utf-8")
        csc = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
        if csc.exists():
            proc = subprocess.run(
                [str(csc), "/nologo", "/optimize+", f"/out:{stub_exe}", str(stub_cs)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0 or not stub_exe.exists():
                raise RuntimeError(f"Failed to compile stub exe with csc.exe: {proc.stdout}\n{proc.stderr}")
        else:
            ps_cmd = (
                f"Add-Type -Path '{stub_cs}' -OutputAssembly '{stub_exe}' -OutputType ConsoleApplication"
            )
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0 or not stub_exe.exists():
                raise RuntimeError(f"Failed to compile stub exe with Add-Type: {proc.stdout}\n{proc.stderr}")

    _CACHED_STUB_EXE = stub_exe

    if min_bytes > 0:
        large_exe = cache_dir / "sh3d_stub_large.exe"
        raw = stub_exe.read_bytes()
        pad_len = max(0, max(min_bytes, 1_100_000) - len(raw))
        large_exe.write_bytes(raw + (b"\x00" * pad_len))
        _CACHED_LARGE_STUB_EXE = large_exe
        return large_exe

    return stub_exe


def install_stub_exe(target_path: Path, *, min_bytes: int = 0) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(get_stub_exe(min_bytes=min_bytes), target_path)
    return target_path


def install_cmd_shim(target_path: Path, exe_name_override: Optional[str] = None) -> Path:
    """Create a .cmd shim (e.g. npm.cmd) that delegates to an accompanying stub .exe."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    stub_name = exe_name_override or (target_path.stem + "_stub.exe")
    stub_exe = target_path.parent / stub_name
    install_stub_exe(stub_exe)
    target_path.write_text(
        f'@echo off\r\n"%~dp0{stub_name}" %*\r\nexit /b %ERRORLEVEL%\r\n',
        encoding="utf-8",
    )
    return target_path


def parse_ps1_ast(ps1_path: Path) -> dict[str, Any]:
    """Parse a PowerShell script via Windows PowerShell 5.1 AST Parser without executing it."""
    if not ps1_path.exists():
        return {"exists": False, "errors": [{"message": f"File not found: {ps1_path}"}], "parameters": [], "has_param_block": False}

    ps_script = r"""
$ErrorActionPreference = 'Stop'
$target = $env:SH3D_AST_TARGET
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($target, [ref]$tokens, [ref]$errors)
$params = @()
$hasParamBlock = $false
if ($ast.ParamBlock -ne $null) {
    $hasParamBlock = $true
    foreach ($p in $ast.ParamBlock.Parameters) {
        $typeNames = @()
        foreach ($attr in $p.Attributes) {
            if ($attr -is [System.Management.Automation.Language.TypeConstraintAst]) {
                $typeNames += $attr.TypeName.Name
            }
        }
        $params += @{
            name = $p.Name.VariablePath.UserPath
            types = $typeNames
        }
    }
}
$errList = @()
foreach ($e in $errors) {
    $errList += @{
        message = $e.Message
        line = $e.Extent.StartLineNumber
        column = $e.Extent.StartColumnNumber
    }
}
@{
    exists = $true
    errors = $errList
    has_param_block = $hasParamBlock
    parameters = $params
} | ConvertTo-Json -Depth 6
"""
    env = os.environ.copy()
    env["SH3D_AST_TARGET"] = str(ps1_path.resolve())
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"PowerShell AST parse failed for {ps1_path}: {proc.stderr}")
    data = json.loads(proc.stdout)
    if isinstance(data.get("errors"), dict):
        data["errors"] = [data["errors"]]
    elif data.get("errors") is None:
        data["errors"] = []
    if isinstance(data.get("parameters"), dict):
        data["parameters"] = [data["parameters"]]
    elif data.get("parameters") is None:
        data["parameters"] = []
    return data


def build_isolated_workspace(
    tmp_path: Path,
    repo_root: Path,
    *,
    include_binaries: bool = True,
    include_venv: bool = True,
    include_dist: bool = True,
    include_node_modules: bool = True,
    env_content: Optional[str] = None,
    include_env_file: bool = False,
) -> dict[str, Any]:
    """Copy scripts/ and safe non-secret repo artifacts into an isolated tmp_path workspace."""
    ws = tmp_path / "repo"
    ws.mkdir(parents=True, exist_ok=True)

    shutil.copytree(repo_root / "scripts", ws / "scripts", dirs_exist_ok=True)

    if (repo_root / ".env.example").exists():
        shutil.copy2(repo_root / ".env.example", ws / ".env.example")

    if (repo_root / "caddy" / "Caddyfile").exists():
        (ws / "caddy").mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / "caddy" / "Caddyfile", ws / "caddy" / "Caddyfile")

    if (repo_root / "go2rtc" / "go2rtc.yaml").exists():
        (ws / "go2rtc").mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / "go2rtc" / "go2rtc.yaml", ws / "go2rtc" / "go2rtc.yaml")

    if (repo_root / "spatial_server" / "requirements.txt").exists():
        (ws / "spatial_server").mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / "spatial_server" / "requirements.txt", ws / "spatial_server" / "requirements.txt")

    for fn in ("package.json", "package-lock.json", "vite.config.js", "index.html"):
        if (repo_root / fn).exists():
            shutil.copy2(repo_root / fn, ws / fn)

    if include_dist:
        (ws / "dist").mkdir(parents=True, exist_ok=True)
        (ws / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
        (ws / "dist" / "sw.js").write_text("// sw\n", encoding="utf-8")

    if include_node_modules:
        (ws / "node_modules").mkdir(parents=True, exist_ok=True)

    if env_content is not None:
        (ws / ".env").write_text(env_content, encoding="utf-8")
    elif include_env_file and (ws / ".env.example").exists():
        shutil.copy2(ws / ".env.example", ws / ".env")

    if include_binaries:
        install_stub_exe(ws / "go2rtc" / "go2rtc.exe", min_bytes=1_100_000)
        install_stub_exe(ws / "caddy" / "caddy.exe", min_bytes=1_100_000)
        install_stub_exe(ws / "tools" / "nssm.exe", min_bytes=150_000)

    if include_venv:
        install_stub_exe(ws / ".venv" / "Scripts" / "python.exe")
        install_stub_exe(ws / ".venv" / "Scripts" / "uvicorn.exe")

    bin_shim = tmp_path / "bin_shim"
    bin_shim.mkdir(parents=True, exist_ok=True)
    for exe_name in ("python.exe", "taskkill.exe", "tasklist.exe", "ping.exe", "sc.exe", "nssm.exe", "git.exe", "net.exe"):
        install_stub_exe(bin_shim / exe_name)
    install_cmd_shim(bin_shim / "npm.cmd", "npm_stub.exe")

    stub_log = tmp_path / "stub_invocations.jsonl"
    ps_log = tmp_path / "ps_shadow_invocations.jsonl"
    sc_state_dir = tmp_path / "sc_state"
    sc_state_dir.mkdir(parents=True, exist_ok=True)

    return {
        "workspace": ws,
        "bin_shim": bin_shim,
        "stub_log": stub_log,
        "ps_log": ps_log,
        "sc_state_dir": sc_state_dir,
    }


def read_jsonl_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def run_ps_dry_run(
    ws_info: dict[str, Any],
    script_rel_path: str,
    script_args: Optional[list[str]] = None,
    *,
    vc_redist_present: bool = True,
    existing_services: Optional[list[str]] = None,
    nssm_status_exit: int = 1,
    mock_fw_exists: bool = False,
    shadow_install_script: bool = False,
    extra_env: Optional[dict[str, str]] = None,
    timeout_s: int = 30,
) -> dict[str, Any]:
    """Run a PowerShell script inside ws_info['workspace'] with full OS-safety function shadows."""
    ws: Path = ws_info["workspace"]
    bin_shim: Path = ws_info["bin_shim"]
    stub_log: Path = ws_info["stub_log"]
    ps_log: Path = ws_info["ps_log"]
    sc_state_dir: Path = ws_info["sc_state_dir"]

    target_script = ws / script_rel_path
    install_script_path = ws / "scripts" / "install_windows_services.ps1"
    orig_install_script_text: Optional[str] = None
    if shadow_install_script and install_script_path.exists():
        orig_install_script_text = install_script_path.read_text(encoding="utf-8")
        install_script_path.write_text(
            "param([string]$LanCidr = '192.168.86.0/24', [switch]$SkipFirewall, [switch]$NoStart)\n"
            "$entry = @{ kind = 'delegated_script'; script = 'install_windows_services.ps1'; args = $MyInvocation.BoundParameters } | ConvertTo-Json -Compress\n"
            "Add-Content -Path $env:SH3D_PS_LOG -Value $entry -Encoding UTF8\n",
            encoding="utf-8",
        )

    args_ps = " ".join(script_args or [])
    harness_ps = ws.parent / "_run_ps_harness.ps1"
    harness_ps.write_text(
        r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.ServiceProcess -ErrorAction SilentlyContinue

function Write-Sh3dShadowLog([string]$Kind, [hashtable]$Data) {
    $payload = @{ kind = $Kind; data = $Data } | ConvertTo-Json -Depth 6 -Compress
    Add-Content -Path $env:SH3D_PS_LOG -Value $payload -Encoding UTF8
}

function New-Object {
    [CmdletBinding()]
    param(
        [Parameter(Position=0, Mandatory=$true)][string]$TypeName,
        [Parameter(Position=1)][object[]]$ArgumentList
    )
    if ($TypeName -eq 'Security.Principal.WindowsPrincipal') {
        $mock = [pscustomobject]@{}
        $mock | Add-Member -MemberType ScriptMethod -Name IsInRole -Value { param($role) return $true }
        return $mock
    }
    if ($PSBoundParameters.ContainsKey('ArgumentList')) {
        return Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName -ArgumentList $ArgumentList
    }
    return Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName
}

function New-NetFirewallRule {
    [CmdletBinding()]
    param(
        [string]$Name,
        [string]$DisplayName,
        [string]$Description,
        [string]$Direction,
        [string]$Action,
        [string]$Protocol,
        $LocalPort,
        $RemoteAddress,
        $Profile,
        $Enabled,
        [switch]$Force
    )
    Write-Sh3dShadowLog 'New-NetFirewallRule' @{
        Name = $Name
        DisplayName = $DisplayName
        Direction = $Direction
        Action = $Action
        Protocol = $Protocol
        LocalPort = $LocalPort
        RemoteAddress = $RemoteAddress
        Profile = $Profile
        Bound = $PSBoundParameters
    }
    return [pscustomobject]@{ Name = $Name; DisplayName = $DisplayName; Protocol = $Protocol; LocalPort = $LocalPort; RemoteAddress = $RemoteAddress }
}

function Get-NetFirewallRule {
    [CmdletBinding()]
    param([string]$Name, [string]$DisplayName)
    Write-Sh3dShadowLog 'Get-NetFirewallRule' @{ Name = $Name; DisplayName = $DisplayName }
    if ($env:SH3D_MOCK_FW_EXISTS -eq '1') {
        return [pscustomobject]@{ Name = $Name; DisplayName = $DisplayName }
    }
    return $null
}

function Remove-NetFirewallRule {
    [CmdletBinding()]
    param([Parameter(ValueFromPipeline=$true)]$InputObject, [string]$Name, [string]$DisplayName)
    Write-Sh3dShadowLog 'Remove-NetFirewallRule' @{ Name = $Name; DisplayName = $DisplayName }
}

function Set-NetFirewallRule {
    [CmdletBinding()]
    param([string]$Name, [string]$DisplayName, $RemoteAddress, $LocalPort, $Protocol)
    Write-Sh3dShadowLog 'Set-NetFirewallRule' @{ Name = $Name; DisplayName = $DisplayName; RemoteAddress = $RemoteAddress }
}

function Invoke-WebRequest {
    [CmdletBinding()]
    param([string]$Uri, [string]$OutFile, [switch]$UseBasicParsing, $Headers, $TimeoutSec)
    Write-Sh3dShadowLog 'Invoke-WebRequest' @{ Uri = $Uri; OutFile = $OutFile }
    if ($OutFile) {
        $dir = Split-Path -Parent $OutFile
        if ($dir -and -not (Microsoft.PowerShell.Management\Test-Path $dir)) {
            Microsoft.PowerShell.Management\New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
        if ($OutFile -like '*.exe') {
            Copy-Item $env:SH3D_LARGE_STUB_EXE $OutFile -Force
        } else {
            [System.IO.File]::WriteAllBytes($OutFile, [byte[]](0x50,0x4B,0x05,0x06) + (New-Object byte[] 60000))
        }
    }
}

function Invoke-RestMethod {
    [CmdletBinding()]
    param([string]$Uri, [string]$OutFile, $Headers, [switch]$UseBasicParsing, $TimeoutSec)
    Write-Sh3dShadowLog 'Invoke-RestMethod' @{ Uri = $Uri; OutFile = $OutFile }
    return [pscustomobject]@{ assets = @([pscustomobject]@{ name = 'caddy_2.9.0_windows_amd64.zip'; browser_download_url = 'https://example.invalid/caddy.zip' }) }
}

function Expand-Archive {
    [CmdletBinding()]
    param([string]$Path, [string]$DestinationPath, [switch]$Force)
    Write-Sh3dShadowLog 'Expand-Archive' @{ Path = $Path; DestinationPath = $DestinationPath }
    if ($DestinationPath) {
        Microsoft.PowerShell.Management\New-Item -ItemType Directory -Force -Path $DestinationPath | Out-Null
        $stub = $env:SH3D_LARGE_STUB_EXE
        if ($Path -match 'caddy') {
            Copy-Item $stub (Join-Path $DestinationPath 'caddy.exe') -Force
        } elseif ($Path -match 'nssm') {
            $sub = Join-Path $DestinationPath 'nssm-2.24\win64'
            Microsoft.PowerShell.Management\New-Item -ItemType Directory -Force -Path $sub | Out-Null
            Copy-Item $stub (Join-Path $sub 'nssm.exe') -Force
            Copy-Item $stub (Join-Path $DestinationPath 'nssm.exe') -Force
        } else {
            Copy-Item $stub (Join-Path $DestinationPath 'go2rtc.exe') -Force
        }
    }
}

function New-Item {
    [CmdletBinding()]
    param(
        [Parameter(Position=0)]$Path,
        [string]$ItemType,
        [switch]$Force,
        $Value
    )
    $pStr = "$Path"
    if ($pStr -like 'HKLM:*' -or $pStr -like 'Registry::*') {
        Write-Sh3dShadowLog 'New-Item' @{ Path = $pStr }
        return [pscustomobject]@{ PSPath = $pStr }
    }
    Microsoft.PowerShell.Management\New-Item @PSBoundParameters
}

function Set-ItemProperty {
    [CmdletBinding()]
    param(
        [Parameter(Position=0)]$Path,
        [string]$Name,
        $Value,
        $Type
    )
    $pStr = "$Path"
    if ($pStr -like 'HKLM:*' -or $pStr -like 'Registry::*') {
        Write-Sh3dShadowLog 'Set-ItemProperty' @{ Path = $pStr; Name = $Name; Value = $Value; Type = "$Type" }
        return
    }
    Microsoft.PowerShell.Management\Set-ItemProperty @PSBoundParameters
}

function Get-ItemProperty {
    [CmdletBinding()]
    param([Parameter(ValueFromPipeline=$true, Position=0)]$Path, [string]$Name)
    $pStr = "$Path"
    if ($pStr -like 'HKLM:*' -or $pStr -like 'Registry::*') {
        Write-Sh3dShadowLog 'Get-ItemProperty' @{ Path = $pStr; Name = $Name }
        if ($env:SH3D_VC_REDIST -eq '1') {
            return [pscustomobject]@{ Installed = 1; Major = 14; Minor = 40; Bld = 33810; Version = '14.40.33810'; DisplayName = 'Microsoft Visual C++ 2015-2022 Redistributable (x64)' }
        }
        return $null
    }
    Microsoft.PowerShell.Management\Get-ItemProperty @PSBoundParameters
}

function Test-Path {
    [CmdletBinding()]
    param([Parameter(Position=0)]$Path, $PathType)
    $pStr = "$Path"
    if ($pStr -match 'vcruntime140' -or $pStr -match 'msvcp140' -or $pStr -like 'HKLM:*') {
        Write-Sh3dShadowLog 'Test-Path' @{ Path = $pStr }
        if ($pStr -like 'HKLM:\SYSTEM\CurrentControlSet\Services\*') { return $true }
        return ($env:SH3D_VC_REDIST -eq '1')
    }
    Microsoft.PowerShell.Management\Test-Path @PSBoundParameters
}

$global:Sh3dStartedServices = New-Object 'System.Collections.Generic.HashSet[string]'

function Get-Service {
    [CmdletBinding()]
    param([Parameter(Position=0)][string[]]$Name)
    Write-Sh3dShadowLog 'Get-Service' @{ Name = $Name }
    $existing = @()
    if ($env:SH3D_MOCK_SERVICES) { $existing = $env:SH3D_MOCK_SERVICES -split ',' }
    $matched = @()
    foreach ($n in $Name) {
        $isStarted = $global:Sh3dStartedServices.Contains($n)
        if ($existing -contains $n -or $isStarted) {
            $statusVal = if ($isStarted) { [System.ServiceProcess.ServiceControllerStatus]::Running } else { [System.ServiceProcess.ServiceControllerStatus]::Stopped }
            $obj = [pscustomobject]@{ Name = $n; Status = $statusVal; StartType = 'Automatic' }
            $obj | Add-Member -MemberType ScriptMethod -Name WaitForStatus -Value { param($targetStatus, $timeout) }
            $matched += $obj
        }
    }
    if ($matched.Count -gt 0) { return $matched }
    if ($PSBoundParameters['ErrorAction'] -eq 'SilentlyContinue' -or $PSBoundParameters['ErrorAction'] -eq 'Ignore') { return $null }
    throw "Cannot find any service with service name '$($Name -join ',')'."
}

function Start-Service {
    [CmdletBinding()]
    param([Parameter(Position=0)][string[]]$Name)
    Write-Sh3dShadowLog 'Start-Service' @{ Name = $Name }
    foreach ($n in $Name) { [void]$global:Sh3dStartedServices.Add($n) }
}

function Stop-Service {
    [CmdletBinding()]
    param([Parameter(Position=0)][string[]]$Name, [switch]$Force)
    Write-Sh3dShadowLog 'Stop-Service' @{ Name = $Name }
}

function Restart-Service {
    [CmdletBinding()]
    param([Parameter(Position=0)][string[]]$Name, [switch]$Force)
    Write-Sh3dShadowLog 'Restart-Service' @{ Name = $Name }
}

function Get-CimInstance {
    [CmdletBinding()]
    param([string]$ClassName, $Filter)
    Write-Sh3dShadowLog 'Get-CimInstance' @{ ClassName = $ClassName }
    return @()
}

function Start-Process {
    [CmdletBinding()]
    param([string]$FilePath, $ArgumentList, [string]$WorkingDirectory, [string]$Verb, [switch]$Wait, [switch]$PassThru, [switch]$NoNewWindow, $WindowStyle)
    Write-Sh3dShadowLog 'Start-Process' @{ FilePath = $FilePath; ArgumentList = $ArgumentList; WorkingDirectory = $WorkingDirectory; Verb = $Verb }
    if ($Verb -eq 'RunAs' -and $env:SH3D_VC_REDIST -ne '1') {
        throw "UAC elevation denied in non-interactive dry-run"
    }
    if ($PassThru) { return [pscustomobject]@{ ExitCode = 0; Id = 99999 } }
}

""" + f'& "{target_script}" {args_ps}\nif ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}\n',
        encoding="utf-8",
    )

    env = os.environ.copy()
    for _k in _ISOLATED_ENV_STRIP_KEYS:
        env.pop(_k, None)
    env["PATH"] = f"{bin_shim};{env.get('PATH', '')}"
    env["SH3D_STUB_LOG"] = str(stub_log)
    env["SH3D_PS_LOG"] = str(ps_log)
    env["SH3D_SC_STATE_DIR"] = str(sc_state_dir)
    env["SH3D_STUB_EXE"] = str(get_stub_exe())
    env["SH3D_LARGE_STUB_EXE"] = str(get_stub_exe(min_bytes=1_100_000))
    env["SH3D_VC_REDIST"] = "1" if vc_redist_present else "0"
    env["SH3D_MOCK_SERVICES"] = ",".join(existing_services or [])
    env["SH3D_NSSM_STATUS_EXIT"] = str(nssm_status_exit)
    env["SH3D_MOCK_FW_EXISTS"] = "1" if mock_fw_exists else "0"
    if extra_env:
        env.update(extra_env)

    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness_ps)],
            cwd=str(ws),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    finally:
        if orig_install_script_text is not None:
            install_script_path.write_text(orig_install_script_text, encoding="utf-8")
    time.sleep(0.15)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "stub_calls": read_jsonl_log(stub_log),
        "ps_calls": read_jsonl_log(ps_log),
    }


_ISOLATED_ENV_STRIP_KEYS: tuple[str, ...] = (
    "SH3D_DEV_MODE",
    "SPATIAL_DEV_AUTH_REQUIRED",
    "VITE_HA_DEV_URL",
    "REOLINK_CARRAIO_PASS",
    "REOLINK_CARRAIO_PASSWORD",
    "REOLINK_PORTICO_PASS",
    "REOLINK_INGRESSO_PASS",
    "REOLINK_STRADINA_PASS",
    "MQTT_PASS",
    "MQTT_PASSWORD",
    "SPATIAL_SERVER_HOST",
    "SPATIAL_SERVER_PORT",
    "SPATIAL_AUTH_REQUIRED",
    "SPATIAL_SESSION_SECRET",
    "SPATIAL_ALLOWED_ORIGINS",
    "GO2RTC_CANDIDATE_LAN",
    "GO2RTC_CANDIDATE_TAILSCALE",
    "BIOMETRICS_ENABLED",
    "VITE_HA_TOKEN",
    "HA_TOKEN",
)


def run_bat_dry_run(
    ws_info: dict[str, Any],
    bat_rel_path: str,
    bat_args: Optional[list[str]] = None,
    *,
    nssm_status_exit: int = 1,
    mock_powershell_exe: bool = True,
    extra_env: Optional[dict[str, str]] = None,
    timeout_s: int = 30,
) -> dict[str, Any]:
    """Run a .bat script inside ws_info['workspace'] with PATH-shimmed stubs."""
    ws: Path = ws_info["workspace"]
    bin_shim: Path = ws_info["bin_shim"]
    stub_log: Path = ws_info["stub_log"]
    sc_state_dir: Path = ws_info["sc_state_dir"]

    if mock_powershell_exe:
        install_stub_exe(bin_shim / "powershell.exe")
    else:
        ps_shim = bin_shim / "powershell.exe"
        if ps_shim.exists():
            ps_shim.unlink()

    bat_path = ws / bat_rel_path
    cmd = ["cmd.exe", "/c", str(bat_path), *(bat_args or [])]

    env = os.environ.copy()
    for _k in _ISOLATED_ENV_STRIP_KEYS:
        env.pop(_k, None)
    env["PATH"] = f"{bin_shim};{env.get('PATH', '')}"
    env["SH3D_STUB_LOG"] = str(stub_log)
    env["SH3D_SC_STATE_DIR"] = str(sc_state_dir)
    env["SH3D_NSSM_STATUS_EXIT"] = str(nssm_status_exit)
    if extra_env:
        env.update(extra_env)

    proc = subprocess.run(
        cmd,
        cwd=str(ws),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    time.sleep(0.35)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "stub_calls": read_jsonl_log(stub_log),
    }
