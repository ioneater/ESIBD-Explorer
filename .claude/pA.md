# DMMR-8 Picoammeter (pA) Plugin Notes

## Overview

The CGC DMMR-8 is a picoammeter controller with up to 8 DPA-1F current measurement modules.
Our setup has 5 modules at addresses 0-4, connected via a single COM port (COM8 on the lab PC).
The ESIBD Explorer plugin is at `esibd/devices/dmmr8/dmmr8.py`.

## Device Class (from esibd_bs)

The PA device class is pip-installed from `esibd_bs` (`pip install -e .` in that repo).
Import path: `from devices.cgc import PA` (via `src/devices/cgc/__init__.py`).

Two-layer class hierarchy:
- `PABase` (`pA_base.py`): Low-level DLL wrapper (ctypes calls to `COM-DMMR-8.dll`)
- `PA` (`pA.py`): Adds logging, housekeeping thread, connect/disconnect convenience methods

The DLL lives at `esibd_bs/src/devices/cgc/pA/DMMR-8_1-02/x64/COM-DMMR-8.dll`.
Error codes JSON at `esibd_bs/src/devices/cgc/error_codes.json`.

## Plugin Architecture

Device-level controller pattern (not per-channel like RBD), because all 5 modules
share one COM port / one PA instance.

Three classes:
- `DMMR8(Device)`: Container, OUTPUTDEVICE type, unit='pA', has charge reset action
- `CurrentChannel(Channel)`: One per module, has Address param (0-7), tracks charge in pAh
- `DMMR8Controller(DeviceController)`: Single controller on the device

## Initialization Sequence (runInitialization)

Must happen in this exact order (verified in notebook 017):
1. `PA("dmmr8_esibd", com=COM_PORT, baudrate=230400)` - create instance
2. `pa.connect()` - opens serial port, sets baud rate
3. `pa.set_enable(True)` - enables all modules
4. `pa.set_automatic_current(True)` - enables continuous measurement mode
5. Emit `initCompleteSignal` to start acquisition loop

## Current Reading (readNumbers)

Uses automatic current mode via `pa.get_current()`:
- Returns `(status, address, current_A, meas_range, timestamp)`
- `status=0 (NO_ERR)`: valid reading, `address` identifies which module
- `status=1 (NO_DATA)`: no new measurement ready, keep polling
- Each call returns ONE module's data; poll in a loop to drain the buffer
- Over time, all modules are polled evenly (verified: 5 min at 2Hz, equal distribution)
- Current is in Amperes, multiply by 1e12 to get pA for display

The readNumbers loop polls get_current() up to NUM_MODULES*3 times per cycle,
breaks on NO_DATA, and maps readings to channels via address-to-index lookup.

## Shutdown Sequence (closeCommunication)

1. `pa.set_automatic_current(False)`
2. `pa.set_enable(False)`
3. `pa.disconnect()` - stops housekeeping, closes port

## Key Gotchas

- **Test Mode**: Settings > General > Test Mode must be OFF for real hardware.
  When on, `fakeInitialization()` runs instead of `runInitialization()` (core.py:5483),
  and `fakeNumbers()` runs instead of `readNumbers()` (core.py:5605).
  The per-channel "R" (Real) column is separate from global Test Mode.

- **Channel count**: The framework doesn't auto-limit to 5 channels. User must
  manually configure exactly 5 channels in the UI and set addresses 0-4.

- **DLL is Windows-only**: PABase uses ctypes.WinDLL, so this plugin only works on Windows.

- **COM port**: Configured in Settings > DMMR8 > COM Port (integer, default 9).
  Lab PC uses COM8.

## PA Class Key Methods Reference

### Connection
- `pa.connect() -> bool` - open port + set baud rate
- `pa.disconnect() -> bool` - stop HK + close port
- `pa.get_status() -> dict` - connection state summary

### Module Control
- `pa.set_enable(bool) -> status` - enable/disable all modules
- `pa.get_enable() -> (status, enabled)`
- `pa.scan_modules() -> dict` - discover connected modules
- `pa.get_module_info(addr) -> dict` - full module snapshot including current

### Current Measurement
- `pa.set_automatic_current(bool) -> status` - enable continuous mode
- `pa.get_current() -> (status, addr, current_A, range, timestamp)` - poll one reading
- `pa.get_module_current(addr) -> (status, current_A, range)` - direct single-module read

### Error Codes
- `NO_ERR = 0`: success
- `NO_DATA = 1`: no new data (not an error, keep polling)
- `ERR_COMMAND_RECEIVE = -10`: device did not respond
- `ERR_NOT_CONNECTED = -100`: port not open

## Testing Reference

Notebook `esibd_bs/debugging/notebooks/017_Testing_pA.ipynb` has the complete
test sequence: connect, enable, scan modules, read currents, automatic polling,
housekeeping, and disconnect. Reference doc: `esibd_bs/src/devices/cgc/pA/pA_reference.md`.
