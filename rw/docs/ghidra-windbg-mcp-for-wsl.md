[← Back to Ravenswatch RE](README.md)

# Ghidra and WinDbg MCP for WSL

This guide sets up Windows-hosted Ghidra and WinDbg MCP servers for use from Codex running inside WSL.

The commands below use Codex because that is the tool configured to connect to MCP servers in this workspace. Other tools need different configuration commands, but the Windows server setup and WSL networking requirements are the same.

The important networking idea is simple: the MCP servers run on Windows, but Codex runs in WSL. For Codex to reach them reliably, WSL needs mirrored networking so `127.0.0.1` from WSL can reach MCP servers listening on Windows.

## Quick Start

Use this when WSL mirrored networking and the MCP entries are already configured.

1. Start Ghidra from Windows PowerShell:

```powershell
& "C:\Tools\Ghidra\ghidraRun.bat"
```

Open the Ravenswatch Ghidra project, open `Ravenswatch.exe` in CodeBrowser, then enable the Ghidra MCP server:

```text
Window -> GhidrAssistMCP
Host: 0.0.0.0
Port: 8080
Server: enabled
```

2. Start WinDbg MCP from Windows PowerShell:

```powershell
py -m mcp_windbg --transport streamable-http --host 0.0.0.0 --port 8000 --timeout 120 --cdb-path "C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe" --symbols-path "SRV*C:\Symbols*https://msdl.microsoft.com/download/symbols" --verbose
```

3. From WSL, verify both endpoints answer:

```bash
curl --max-time 5 -i http://127.0.0.1:8080/mcp
curl --max-time 5 -i http://127.0.0.1:8000/mcp
```

For Ghidra, `400 Bad Request` from raw curl is fine. For WinDbg, any HTTP response is enough; a redirect to `/mcp/` is fine.

4. Resume Codex from the repo so it handshakes with the running MCP servers:

```bash
cd /home/ks73/repos/work/ravensmith
codex resume --last
```

## Setup Order

1. Enable WSL mirrored networking.
2. Restart WSL completely.
3. Start the Windows-side MCP server.
4. Test the MCP endpoint from WSL.
5. Add the MCP endpoint to Codex.
6. Restart/resume Codex.

## WSL Networking

Create or edit this file on Windows:

```text
C:\Users\<you>\.wslconfig
```

Use this configuration:

```ini
[wsl2]
networkingMode=mirrored
# localhostForwarding=true
# firewall=true
```

For this workspace, `networkingMode=mirrored` is the required fix. Leave `localhostForwarding=true` and `firewall=true` commented out; enabling them caused errors in this environment.

After saving `.wslconfig`, restart WSL from Windows PowerShell:

```powershell
wsl --shutdown
```

Then reopen WSL from the repo and resume Codex:

```bash
cd /home/ks73/repos/work/ravensmith
codex resume --last
```

## Connectivity Test

After WSL has restarted and a Windows MCP server is running, test from WSL:

```bash
curl --max-time 5 -i http://127.0.0.1:8080/mcp
```

For Ghidra MCP, this raw curl request normally returns:

```text
HTTP/1.1 400 Bad Request
```

That response is enough for the networking check. It proves the request left WSL, reached the Windows MCP listener, and got a response back. The `400` happens because curl is not starting a real MCP session; it is only probing the HTTP endpoint. Once Codex is configured to use the server, the normal MCP connection flow handles the actual session.

If Windows can reach the endpoint but WSL cannot, revisit the mirrored networking step and make sure WSL was fully restarted with `wsl --shutdown`.

## Ghidra MCP

Use [GhidrAssistMCP](https://github.com/symgraph/GhidrAssistMCP).

Windows setup:

1. Install Java and Ghidra.
2. Extract Ghidra somewhere outside the WSL repo.
3. Download the latest GhidrAssistMCP ZIP from the [GhidrAssistMCP releases page](https://github.com/symgraph/GhidrAssistMCP/releases).
4. In Ghidra, install the extension:

Start Ghidra from Windows PowerShell:

```powershell
& "C:\Tools\Ghidra\ghidraRun.bat"
```

```text
File -> Install Extensions -> Add Extension
restart Ghidra
File -> Configure -> Configure Plugins
enable GhidrAssistMCP
Window -> GhidrAssistMCP
```

Configure the GhidrAssistMCP panel:

```text
Host: 0.0.0.0
Port: 8080
Server: enabled
```

Import `Ravenswatch.exe` into a Windows-native Ghidra project. Do not put the Ghidra project inside the WSL repo. Keep the target program open in CodeBrowser while Codex is using the MCP server.

Optional Windows-side smoke test:

```powershell
curl.exe -i http://127.0.0.1:8080/mcp
```

Then run the WSL-side test from the previous section. The WSL-side test is the one that matters for Codex.

Add the server to Codex from WSL:

```bash
codex mcp add ghidra --url http://127.0.0.1:8080/mcp
codex mcp list
```

Expected listing:

```text
ghidra  http://127.0.0.1:8080/mcp  enabled
```

Restart/resume Codex after adding the server. A running Codex process does not dynamically load newly added MCP servers.

## WinDbg MCP

Use [mcp-windbg](https://github.com/svnscha/mcp-windbg).

Windows prerequisites:

- Debugging Tools for Windows from the Windows SDK installer.
- Python 3.10 or newer.

The WinDbg MCP server launches `cdb.exe`, the Console Debugger. Installing the WinDbg GUI alone is not enough if `cdb.exe` is missing. In the Windows SDK installer, select **Debugging Tools for Windows**; the other SDK components are not needed for this setup.

Verify that CDB exists:

```powershell
Test-Path "C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe"
```

Expected result:

```text
True
```

Install:

```powershell
py -m pip install mcp-windbg
```

Start the MCP server:

```powershell
py -m mcp_windbg --transport streamable-http --host 0.0.0.0 --port 8000 --timeout 120 --cdb-path "C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe" --symbols-path "SRV*C:\Symbols*https://msdl.microsoft.com/download/symbols" --verbose
```

This guide uses `--cdb-path` intentionally. It avoids requiring `cdb.exe` to be on `PATH` and fixes the common server error:

```text
Failed to create CDB session: Could not find cdb.exe. Please provide a valid path.
```

The `--symbols-path` argument is passed to the CDB/WinDbg engine that `mcp_windbg` launches. It caches Microsoft public symbols in `C:\Symbols`. Ravenswatch private symbols are not expected, but Windows/system-library symbols make stacks and exception analysis clearer.

If `cdb.exe` is on `PATH`, `--cdb-path` can be omitted, but the explicit path is more reproducible.

Optional user PATH setup:

```powershell
$debuggerPath = "C:\Program Files (x86)\Windows Kits\10\Debuggers\x64"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")

if (($userPath -split ';') -notcontains $debuggerPath) {
    $newPath = (($userPath.TrimEnd(';') + ';' + $debuggerPath).TrimStart(';'))
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
}
```

After changing PATH, close and reopen PowerShell, then verify:

```powershell
where.exe cdb
```

The shorter command below also works if `cdb.exe` is on `PATH` and symbol configuration is handled elsewhere:

```powershell
py -m mcp_windbg --transport streamable-http --host 0.0.0.0 --port 8000 --timeout 120 --verbose
```

Successful startup looks like:

```text
MCP WinDbg server running on http://0.0.0.0:8000
MCP endpoint: http://0.0.0.0:8000/mcp
Uvicorn running on http://0.0.0.0:8000
```

If startup fails with `WinError 10048` / "only one usage of each socket address", another process is already listening on port `8000`. Find and stop it:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess
Get-Process -Id <OwningProcess>
Stop-Process -Id <OwningProcess>
```

Test from WSL:

```bash
curl --max-time 5 -i http://127.0.0.1:8000/mcp
```

Any HTTP response from this command proves WSL can reach the Windows-side WinDbg MCP listener. A `307 Temporary Redirect` to `/mcp/` is fine. A timeout or connection refusal means the server is not running or the networking path is still broken.

Add the server to Codex from WSL:

```bash
codex mcp add windbg --url http://127.0.0.1:8000/mcp
codex mcp list
```

Expected listing:

```text
windbg  http://127.0.0.1:8000/mcp  enabled
```

Restart/resume Codex after adding the server.

## Working Endpoints

```text
Ghidra: http://127.0.0.1:8080/mcp
WinDbg: http://127.0.0.1:8000/mcp
```

Keep the Windows-side MCP server windows running while Codex is using them.

## Notes

Binding to `0.0.0.0` makes the server listen on all interfaces. Use this only on a trusted machine/network, or add firewall rules that restrict access.

For Ghidra, prefer serialized MCP calls. Ghidra has shared UI/project state, so parallel calls can produce confusing results.
