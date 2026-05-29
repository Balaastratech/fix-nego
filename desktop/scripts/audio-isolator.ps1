# audio-isolator.ps1
# Driverless per-process mic isolation via Windows IAudioPolicyConfig + IPolicyConfig COM.
# Runs in server mode: reads JSON commands from stdin, writes JSON responses to stdout.
# This avoids per-call PowerShell startup overhead — one process stays alive per session.
#
# MUST be launched with -Sta: Windows audio COM objects are apartment-threaded; in the
# default MTA, CoCreateInstance/enumerate silently return nothing.
#
# Commands (JSON objects, one per line via stdin):
#   { "cmd": "init" }
#   { "cmd": "enumerate" }                                         → capture endpoints + states
#   { "cmd": "pid-from-hwnd", "hwnd": "12345" }
#   { "cmd": "probe", "pid": 123, "listenerDeviceId": "{...}" }    → choose silent-target method
#   { "cmd": "redirect", "pid": 12345, "deviceId": "{0.0.1...}" }  → IAudioPolicyConfig
#   { "cmd": "restore",  "pid": 12345 }
#   { "cmd": "set-visibility", "deviceId": "{...}", "visible": 0 } → IPolicyConfig (disable/enable)
#   { "cmd": "send-keys", "combo": "alt+a" }
#   { "cmd": "exit" }
#
# Response format: { "ok": true/false, "error": null/"...", ...extra fields... }

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8

# ── Compile the C# COM interop types once on startup ─────────────────────────
$typeSource = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

// ── WASAPI enums ──────────────────────────────────────────────────────────────
public enum EDataFlow { eRender = 0, eCapture = 1, eAll = 2 }
public enum ERole    { eConsole = 0, eMultimedia = 1, eCommunications = 2 }

[Flags]
public enum DeviceState : uint {
    Active     = 0x1,
    Disabled   = 0x2,
    NotPresent = 0x4,
    Unplugged  = 0x8,
    All        = 0xF
}

// ── PROPVARIANT (minimal — only VT_LPWSTR = 31 used) ─────────────────────────
// Actual PROPVARIANT on x64 is 24 bytes:
//   8 bytes header (vt + 3 reserved WORDs)
//   16 bytes data union (largest member is CA* vector type: ULONG + pointer = 4+4pad+8)
// Using Size=16 would cause GetValue to overwrite adjacent memory. Use Size=24.
[StructLayout(LayoutKind.Explicit, Size = 24)]
public struct PROPVARIANT {
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr ptrVal;   // VT_LPWSTR (vt==31): pointer to wide string
    [FieldOffset(8)] public long   hVal;     // VT_I8 / VT_UI8
}

[StructLayout(LayoutKind.Sequential)]
public struct PROPERTYKEY {
    public Guid   fmtid;
    public uint   pid;
}

// ── IPropertyStore ────────────────────────────────────────────────────────────
[ComImport]
[Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPropertyStore {
    [PreserveSig] int GetCount(out uint cProps);
    [PreserveSig] int GetAt(uint iProp, out PROPERTYKEY pkey);
    [PreserveSig] int GetValue(ref PROPERTYKEY key, out PROPVARIANT pv);
    [PreserveSig] int SetValue(ref PROPERTYKEY key, ref PROPVARIANT propvar);
    [PreserveSig] int Commit();
}

// ── IMMDevice ─────────────────────────────────────────────────────────────────
[ComImport]
[Guid("D666063F-1587-4E43-81F1-B948E807363F")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDevice {
    [PreserveSig] int Activate(ref Guid iid, uint dwClsCtx, IntPtr pActivationParams,
        [MarshalAs(UnmanagedType.IUnknown)] out object ppInterface);
    [PreserveSig] int OpenPropertyStore(uint stgmAccess, out IPropertyStore ppProperties);
    [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string strId);
    [PreserveSig] int GetState(out DeviceState pdwState);
}

// ── IMMDeviceCollection ───────────────────────────────────────────────────────
[ComImport]
[Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDeviceCollection {
    [PreserveSig] int GetCount(out uint pcDevices);
    [PreserveSig] int Item(uint nDevice, out IMMDevice ppDevice);
}

// ── IMMDeviceEnumerator ───────────────────────────────────────────────────────
[ComImport]
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDeviceEnumerator {
    [PreserveSig] int EnumAudioEndpoints(EDataFlow dataFlow, DeviceState stateMask,
        out IMMDeviceCollection ppDevices);
    [PreserveSig] int GetDefaultAudioEndpoint(EDataFlow dataFlow, ERole role,
        out IMMDevice ppEndpoint);
    [PreserveSig] int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string pwstrId,
        out IMMDevice ppDevice);
    [PreserveSig] int RegisterEndpointNotificationCallback(IntPtr pClient);
    [PreserveSig] int UnregisterEndpointNotificationCallback(IntPtr pClient);
}

// ── MMDeviceEnumerator COM class ──────────────────────────────────────────────
// Note: No [ClassInterface] here — that attribute is for .NET classes EXPORTING to COM,
// not for [ComImport] classes. Adding it incorrectly can confuse the CLR's COM activator.
[ComImport]
[Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
public class MMDeviceEnumeratorClass { }

// ── IAudioPolicyConfig — WinRT IInspectable-derived factory ──────────────────
// CRITICAL: this is an IInspectable interface (activated via RoGetActivationFactory),
// NOT IUnknown. With InterfaceIsIInspectable the CLR auto-prepends the 6 IInspectable
// vtable slots (IUnknown 3 + GetIids/GetRuntimeClassName/GetTrustLevel). There are then
// 19 reverse-engineered placeholder methods before SetPersistedDefaultAudioEndpoint.
// Getting this count wrong = wrong vtable slot = AccessViolation. Win10 & Win11 share the
// same layout; they differ ONLY by IID. (Source: Belphemur/SoundSwitch, widely-used gist.)

// Win11 / Win10 21H2+ — IID ab3d4648-…
[ComImport]
[Guid("ab3d4648-e242-459f-b02f-541c70306324")]
[InterfaceType(ComInterfaceType.InterfaceIsIInspectable)]
public interface IAudioPolicyConfigWin11 {
    int __incomplete__add_CtxVolumeChange();
    int __incomplete__remove_CtxVolumeChanged();
    int __incomplete__add_RingerVibrateStateChanged();
    int __incomplete__remove_RingerVibrateStateChange();
    int __incomplete__SetVolumeGroupGainForId();
    int __incomplete__GetVolumeGroupGainForId();
    int __incomplete__GetActiveVolumeGroupForEndpointId();
    int __incomplete__GetVolumeGroupsForEndpoint();
    int __incomplete__GetCurrentVolumeContext();
    int __incomplete__SetVolumeGroupMuteForId();
    int __incomplete__GetVolumeGroupMuteForId();
    int __incomplete__SetRingerVibrateState();
    int __incomplete__GetRingerVibrateState();
    int __incomplete__SetPreferredChatApplication();
    int __incomplete__ResetPreferredChatApplication();
    int __incomplete__GetPreferredChatApplication();
    int __incomplete__GetCurrentChatApplications();
    int __incomplete__add_ChatContextChanged();
    int __incomplete__remove_ChatContextChanged();
    // deviceId passed as a manually-created HSTRING (IntPtr) — the automatic
    // UnmanagedType.HString marshaller misbehaves under .NET Framework (E_INVALIDARG).
    [PreserveSig] int SetPersistedDefaultAudioEndpoint(
        uint processId, EDataFlow flow, ERole role, IntPtr deviceId);
    [PreserveSig] int GetPersistedDefaultAudioEndpoint(
        uint processId, EDataFlow flow, ERole role, out IntPtr deviceId);
    [PreserveSig] int ClearAllPersistedApplicationDefaultEndpoints();
}

// Win10 pre-21H2 — IID 2a59116d-… (identical layout, different IID)
[ComImport]
[Guid("2a59116d-6c4f-45e0-a74f-707e3fef9258")]
[InterfaceType(ComInterfaceType.InterfaceIsIInspectable)]
public interface IAudioPolicyConfigWin10 {
    int __incomplete__add_CtxVolumeChange();
    int __incomplete__remove_CtxVolumeChanged();
    int __incomplete__add_RingerVibrateStateChanged();
    int __incomplete__remove_RingerVibrateStateChange();
    int __incomplete__SetVolumeGroupGainForId();
    int __incomplete__GetVolumeGroupGainForId();
    int __incomplete__GetActiveVolumeGroupForEndpointId();
    int __incomplete__GetVolumeGroupsForEndpoint();
    int __incomplete__GetCurrentVolumeContext();
    int __incomplete__SetVolumeGroupMuteForId();
    int __incomplete__GetVolumeGroupMuteForId();
    int __incomplete__SetRingerVibrateState();
    int __incomplete__GetRingerVibrateState();
    int __incomplete__SetPreferredChatApplication();
    int __incomplete__ResetPreferredChatApplication();
    int __incomplete__GetPreferredChatApplication();
    int __incomplete__GetCurrentChatApplications();
    int __incomplete__add_ChatContextChanged();
    int __incomplete__remove_ChatContextChanged();
    // deviceId passed as a manually-created HSTRING (IntPtr) — the automatic
    // UnmanagedType.HString marshaller misbehaves under .NET Framework (E_INVALIDARG).
    [PreserveSig] int SetPersistedDefaultAudioEndpoint(
        uint processId, EDataFlow flow, ERole role, IntPtr deviceId);
    [PreserveSig] int GetPersistedDefaultAudioEndpoint(
        uint processId, EDataFlow flow, ERole role, out IntPtr deviceId);
    [PreserveSig] int ClearAllPersistedApplicationDefaultEndpoints();
}

// ── AudioPolicyConfigFactory COM class — CLSID: 1776dbe8-... ─────────────────
[ComImport]
[Guid("1776dbe8-7514-4cf4-9d3c-4f452b4c5bdc")]
public class AudioPolicyConfigFactory { }

// ── IPolicyConfig (Win7+) — IID f8679f50-… — for SetEndpointVisibility ───────
// The exact COM interface the Sound Control Panel uses to disable/enable a device.
// No admin: it RPCs into audiosrv (SYSTEM). ALL preceding methods must be declared
// so SetEndpointVisibility lands at the correct vtable slot (last). We never call the
// placeholders, so their signatures only need to occupy a slot in declaration order.
[ComImport]
[Guid("f8679f50-850a-41cf-9c72-430f290290c8")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPolicyConfig {
    [PreserveSig] int GetMixFormat(IntPtr a, IntPtr b);
    [PreserveSig] int GetDeviceFormat(IntPtr a, int b, IntPtr c);
    [PreserveSig] int ResetDeviceFormat(IntPtr a);
    [PreserveSig] int SetDeviceFormat(IntPtr a, IntPtr b, IntPtr c);
    [PreserveSig] int GetProcessingPeriod(IntPtr a, int b, IntPtr c, IntPtr d);
    [PreserveSig] int SetProcessingPeriod(IntPtr a, IntPtr b);
    [PreserveSig] int GetShareMode(IntPtr a, IntPtr b);
    [PreserveSig] int SetShareMode(IntPtr a, IntPtr b);
    [PreserveSig] int GetPropertyValue(IntPtr a, int b, IntPtr c, IntPtr d);
    [PreserveSig] int SetPropertyValue(IntPtr a, int b, IntPtr c, IntPtr d);
    [PreserveSig] int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string deviceId, ERole role);
    [PreserveSig] int SetEndpointVisibility([MarshalAs(UnmanagedType.LPWStr)] string deviceId, int visible);
}

// CPolicyConfigClient — CLSID 870af99c-…
[ComImport]
[Guid("870af99c-171d-4f9e-af0d-e63df40c2bc9")]
public class CPolicyConfigClient { }

// ── IPolicyConfigVista (Vista/older builds) — IID 568b9108-… ─────────────────
[ComImport]
[Guid("568b9108-44bf-40b4-9006-86afe5b5a620")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPolicyConfigVista {
    [PreserveSig] int GetMixFormat(IntPtr a, IntPtr b);
    [PreserveSig] int GetDeviceFormat(IntPtr a, int b, IntPtr c);
    [PreserveSig] int SetDeviceFormat(IntPtr a, IntPtr b, IntPtr c);
    [PreserveSig] int GetProcessingPeriod(IntPtr a, int b, IntPtr c, IntPtr d);
    [PreserveSig] int SetProcessingPeriod(IntPtr a, IntPtr b);
    [PreserveSig] int GetShareMode(IntPtr a, IntPtr b);
    [PreserveSig] int SetShareMode(IntPtr a, IntPtr b);
    [PreserveSig] int GetPropertyValue(IntPtr a, int b, IntPtr c, IntPtr d);
    [PreserveSig] int SetPropertyValue(IntPtr a, int b, IntPtr c, IntPtr d);
    [PreserveSig] int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string deviceId, ERole role);
    [PreserveSig] int SetEndpointVisibility([MarshalAs(UnmanagedType.LPWStr)] string deviceId, int visible);
}

// CPolicyConfigVistaClient — CLSID 294935CE-…
[ComImport]
[Guid("294935CE-F637-4E7C-A41B-AB255460B862")]
public class CPolicyConfigVistaClient { }

// ── P/Invoke helpers ──────────────────────────────────────────────────────────
public static class NativeHelpers {
    [DllImport("user32.dll", SetLastError = true)]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll")]
    public static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    // ── combase / WinRT activation (IAudioPolicyConfig is a WinRT-activated class) ──
    [DllImport("combase.dll", PreserveSig = true)]
    static extern int RoInitialize(int initType);
    [DllImport("combase.dll", PreserveSig = true, CharSet = CharSet.Unicode)]
    static extern int WindowsCreateString(string sourceString, int length, out IntPtr hstring);
    [DllImport("combase.dll", PreserveSig = true)]
    static extern int WindowsDeleteString(IntPtr hstring);
    [DllImport("combase.dll", PreserveSig = true)]
    static extern int RoGetActivationFactory(IntPtr activatableClassId, [In] ref Guid iid, out IntPtr factory);

    [StructLayout(LayoutKind.Sequential)]
    public struct KEYBDINPUT {
        public ushort wVk;
        public ushort wScan;
        public uint   dwFlags;
        public uint   time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct INPUT {
        public uint       type;       // INPUT_KEYBOARD = 1
        public KEYBDINPUT ki;
    }

    public const uint  INPUT_KEYBOARD    = 1;
    public const uint  KEYEVENTF_KEYUP   = 0x0002;

    // Read PKEY_Device_FriendlyName (fmtid={a45c254e-...}, pid=14) from IPropertyStore
    public static string GetFriendlyName(IMMDevice device) {
        try {
            IPropertyStore store;
            if (device.OpenPropertyStore(0 /*STGM_READ*/, out store) != 0) return null;
            var key = new PROPERTYKEY {
                fmtid = new Guid("a45c254e-df1c-4efd-8020-67d146a850e0"),
                pid   = 14
            };
            PROPVARIANT pv;
            if (store.GetValue(ref key, out pv) != 0) return null;
            if (pv.vt == 31 && pv.ptrVal != IntPtr.Zero) // VT_LPWSTR
                return Marshal.PtrToStringUni(pv.ptrVal);
            return null;
        } catch { return null; }
    }

    // ── Self-contained orchestration ────────────────────────────────────────
    // IMPORTANT: All COM interface calls live HERE in C#, not in PowerShell.
    // PowerShell cannot invoke IUnknown-only COM interface methods (it routes COM
    // through IDispatch, which these audio interfaces don't implement). So PS only
    // calls these simple static methods that return strings/ints.

    static IMMDeviceEnumerator _enum;
    static object  _policyCfg;       // IAudioPolicyConfigWin11 or Win10
    static string  _policyVersion;   // "win11" | "win10" | "none"

    static IMMDeviceEnumerator Enumerator() {
        if (_enum == null) _enum = (IMMDeviceEnumerator)new MMDeviceEnumeratorClass();
        return _enum;
    }

    // Initialize policy config via WinRT activation; returns the version tag that activated.
    public static string Init() {
        if (_policyCfg == null) {
            try { RoInitialize(0); } catch { } // RO_INIT_SINGLETHREADED; ignore if already init
            IntPtr hstr = IntPtr.Zero;
            try {
                const string cls = "Windows.Media.Internal.AudioPolicyConfig";
                if (WindowsCreateString(cls, cls.Length, out hstr) == 0 && hstr != IntPtr.Zero) {
                    // Win11/21H2+ IID first
                    Guid iid11 = typeof(IAudioPolicyConfigWin11).GUID;
                    IntPtr pf;
                    if (RoGetActivationFactory(hstr, ref iid11, out pf) == 0 && pf != IntPtr.Zero) {
                        try { _policyCfg = Marshal.GetObjectForIUnknown(pf) as IAudioPolicyConfigWin11; }
                        finally { Marshal.Release(pf); }
                        if (_policyCfg != null) _policyVersion = "win11";
                    }
                    // Win10 pre-21H2 IID
                    if (_policyCfg == null) {
                        Guid iid10 = typeof(IAudioPolicyConfigWin10).GUID;
                        IntPtr pf2;
                        if (RoGetActivationFactory(hstr, ref iid10, out pf2) == 0 && pf2 != IntPtr.Zero) {
                            try { _policyCfg = Marshal.GetObjectForIUnknown(pf2) as IAudioPolicyConfigWin10; }
                            finally { Marshal.Release(pf2); }
                            if (_policyCfg != null) _policyVersion = "win10";
                        }
                    }
                }
            } catch { }
            finally { if (hstr != IntPtr.Zero) WindowsDeleteString(hstr); }

            // Last-resort: legacy CoCreate on the factory CLSID (some early builds)
            if (_policyCfg == null) {
                try {
                    var f = new AudioPolicyConfigFactory();
                    var w11 = f as IAudioPolicyConfigWin11;
                    if (w11 != null) { _policyCfg = w11; _policyVersion = "win11"; }
                    else {
                        var w10 = f as IAudioPolicyConfigWin10;
                        if (w10 != null) { _policyCfg = w10; _policyVersion = "win10"; }
                    }
                } catch { }
            }

            if (_policyVersion == null) _policyVersion = "none";
        }
        Enumerator(); // warm
        return _policyVersion ?? "none";
    }

    public static string PolicyVersion() { return _policyVersion ?? "none"; }

    // Returns one line per capture endpoint: "id\tname\tstate\tisDefault"
    public static string[] EnumerateCapture() {
        var enumr = Enumerator();
        IMMDeviceCollection coll;
        int hr = enumr.EnumAudioEndpoints(EDataFlow.eCapture, DeviceState.All, out coll);
        if (hr != 0) throw new Exception("EnumAudioEndpoints hr=0x" + hr.ToString("X8"));

        string defaultId = null;
        try {
            IMMDevice def;
            if (enumr.GetDefaultAudioEndpoint(EDataFlow.eCapture, ERole.eCommunications, out def) == 0)
                def.GetId(out defaultId);
        } catch { }

        uint count; coll.GetCount(out count);
        var rows = new List<string>();
        for (uint i = 0; i < count; i++) {
            IMMDevice dev;
            if (coll.Item(i, out dev) != 0) continue;
            string id; dev.GetId(out id);
            DeviceState st; dev.GetState(out st);
            string state =
                st == DeviceState.Active     ? "active" :
                st == DeviceState.Disabled   ? "disabled" :
                st == DeviceState.NotPresent ? "not_present" :
                st == DeviceState.Unplugged  ? "unplugged" : "unknown";
            string name = GetFriendlyName(dev) ?? "Unknown";
            bool isDef = (id == defaultId);
            // tab-delimited; names can't realistically contain tabs
            rows.Add(id + "\t" + name + "\t" + state + "\t" + (isDef ? "1" : "0"));
        }
        return rows.ToArray();
    }

    // Redirect a process's capture to deviceId for all three roles. deviceId "" = restore default.
    // Returns 0 on full success, else the first non-zero HRESULT.
    const string CAPTURE_IFACE = "{2eef81be-33fa-4800-9670-1cd474972c3f}"; // eCapture interface class

    // Wrap a bare endpoint id "{0.0.1.00000000}.{guid}" into the device-path form
    // \\?\SWD#MMDEVAPI#<bareId>#{2eef81be-...} that the persisted-endpoint API expects.
    static string WrapEndpointPath(string bareId) {
        if (string.IsNullOrEmpty(bareId)) return bareId;
        if (bareId.IndexOf("SWD#MMDEVAPI#", StringComparison.OrdinalIgnoreCase) >= 0) return bareId;
        return @"\\?\SWD#MMDEVAPI#" + bareId + "#" + CAPTURE_IFACE;
    }

    static int SetPersistedForAllRoles(uint pid, string deviceId) {
        IntPtr h = IntPtr.Zero;
        int cr = WindowsCreateString(deviceId ?? "", (deviceId ?? "").Length, out h);
        if (cr != 0) return cr;
        try {
            ERole[] roles = { ERole.eConsole, ERole.eMultimedia, ERole.eCommunications };
            foreach (var role in roles) {
                int hr;
                if (_policyVersion == "win11")
                    hr = ((IAudioPolicyConfigWin11)_policyCfg).SetPersistedDefaultAudioEndpoint(pid, EDataFlow.eCapture, role, h);
                else
                    hr = ((IAudioPolicyConfigWin10)_policyCfg).SetPersistedDefaultAudioEndpoint(pid, EDataFlow.eCapture, role, h);
                if (hr != 0) return hr;
            }
            return 0;
        } finally {
            if (h != IntPtr.Zero) WindowsDeleteString(h);
        }
    }

    // Redirect a process's capture to deviceId for all roles. "" = restore default.
    // Tries the id as-given, then (on E_INVALIDARG for a non-empty bare id) the SWD-wrapped
    // device-path form — the format the persisted-endpoint API actually expects.
    public static int Redirect(uint pid, string deviceId) {
        if (_policyCfg == null) Init();
        if (_policyCfg == null) return unchecked((int)0x80004002);
        if (deviceId == null) deviceId = "";

        int hr = SetPersistedForAllRoles(pid, deviceId);
        const int E_INVALIDARG = unchecked((int)0x80070057);
        if (hr == E_INVALIDARG && deviceId.Length > 0 &&
            deviceId.IndexOf("SWD#MMDEVAPI#", StringComparison.OrdinalIgnoreCase) < 0) {
            // Retry with the device-path form
            hr = SetPersistedForAllRoles(pid, WrapEndpointPath(deviceId));
        }
        return hr;
    }

    // Parse a combo like "alt+a" / "ctrl+shift+m" and send key-down (all) + key-up (reverse)
    // via SendInput. Returns the number of inputs accepted (0 = failure). All done in C# to
    // avoid PowerShell type-accelerator pitfalls ([ushort] etc.).
    public static int SendKeyCombo(string combo) {
        if (string.IsNullOrEmpty(combo)) return 0;
        var parts = combo.ToLower().Split('+');
        var vks = new List<ushort>();
        ushort mainKey = 0;
        foreach (var raw in parts) {
            var p = raw.Trim();
            if (p.Length == 0) continue;
            ushort vk;
            if (p == "alt")        vk = 0x12;
            else if (p == "ctrl")  vk = 0x11;
            else if (p == "shift") vk = 0x10;
            else if (p == "win")   vk = 0x5B;
            else if (p.Length == 1) { mainKey = (ushort)char.ToUpper(p[0]); continue; }
            else continue;
            vks.Add(vk); // modifier
        }
        if (mainKey == 0) return 0;

        var order = new List<ushort>(vks); order.Add(mainKey); // modifiers then main
        var inputs = new List<INPUT>();
        foreach (var vk in order) {
            var d = new INPUT { type = INPUT_KEYBOARD, ki = new KEYBDINPUT { wVk = vk } };
            inputs.Add(d);
        }
        for (int i = order.Count - 1; i >= 0; i--) {
            var u = new INPUT { type = INPUT_KEYBOARD, ki = new KEYBDINPUT { wVk = order[i], dwFlags = KEYEVENTF_KEYUP } };
            inputs.Add(u);
        }
        var arr = inputs.ToArray();
        return (int)SendInput((uint)arr.Length, arr, Marshal.SizeOf(typeof(INPUT)));
    }

    // SetEndpointVisibility via IPolicyConfig (CPolicyConfigClient), Vista fallback.
    // visible: 0 = disable, 1 = enable. Returns HRESULT (0 = ok) or E_NOINTERFACE sentinel.
    public static int SetEndpointVisibility(string deviceId, int visible) {
        try {
            var cfg = new CPolicyConfigClient() as IPolicyConfig;
            if (cfg != null) return cfg.SetEndpointVisibility(deviceId, visible);
        } catch { }
        try {
            var cfgV = new CPolicyConfigVistaClient() as IPolicyConfigVista;
            if (cfgV != null) return cfgV.SetEndpointVisibility(deviceId, visible);
        } catch { }
        return unchecked((int)0x80004002);
    }
}
'@

try {
    Add-Type -TypeDefinition $typeSource -Language CSharp -ReferencedAssemblies `
        'System.Runtime.InteropServices' -ErrorAction Stop
} catch {
    $err = @{ ok = $false; error = "Add-Type failed: $_" } | ConvertTo-Json -Compress
    [Console]::WriteLine($err)
    exit 1
}

# ── Init (warms COM singletons inside C#) ─────────────────────────────────────
$script:PolicyVersion = $null
function Initialize-Native {
    if ($null -eq $script:PolicyVersion) {
        $script:PolicyVersion = [NativeHelpers]::Init()
    }
    return $script:PolicyVersion
}

# ── enumerate command (all COM done in C#; PS just parses tab-delimited rows) ──
function Invoke-Enumerate {
    Initialize-Native | Out-Null
    try {
        $rows = [NativeHelpers]::EnumerateCapture()
    } catch {
        return @{ ok = $false; error = "EnumerateCapture failed: $_" }
    }
    $devices = @()
    foreach ($row in $rows) {
        if ([string]::IsNullOrEmpty($row)) { continue }
        $parts = $row -split "`t", 4
        if ($parts.Count -lt 4) { continue }
        $devices += @{
            id        = $parts[0]
            name      = $parts[1]
            state     = $parts[2]
            isDefault = ($parts[3] -eq '1')
        }
    }
    return @{ ok = $true; devices = $devices; policyVersion = $script:PolicyVersion }
}

# ── pid-from-hwnd command ─────────────────────────────────────────────────────
function Invoke-PidFromHwnd([string]$hwndStr) {
    try {
        $hwnd = [System.IntPtr]::new([long]$hwndStr)
        $procId = [uint32]0
        $tid  = [NativeHelpers]::GetWindowThreadProcessId($hwnd, [ref]$procId)
        if ($tid -eq 0 -or $procId -eq 0) {
            return @{ ok = $false; error = "GetWindowThreadProcessId returned 0" }
        }
        return @{ ok = $true; pid = [int]$procId }
    } catch {
        return @{ ok = $false; error = "pid-from-hwnd error: $_" }
    }
}

# ── redirect/restore helpers (COM in C#) ──────────────────────────────────────
function Set-AudioEndpoint([uint32]$procId, [string]$deviceId) {
    Initialize-Native | Out-Null
    if ($script:PolicyVersion -eq 'none') {
        return @{ ok = $false; error = "IAudioPolicyConfig unavailable (factory activation failed)" }
    }
    try {
        $hr = [NativeHelpers]::Redirect($procId, $deviceId)
    } catch {
        return @{ ok = $false; error = "Redirect exception: $_" }
    }
    if ($hr -ne 0) {
        return @{ ok = $false; error = "Redirect hr=0x$([int]$hr.ToString('X8'))"; hr = $hr }
    }
    return @{ ok = $true; pid = [int]$procId; deviceId = $deviceId }
}

# ── set-visibility command (disable/enable a device) ─────────────────────────
function Invoke-SetVisibility([string]$deviceId, [int]$visible) {
    if ([string]::IsNullOrEmpty($deviceId)) {
        return @{ ok = $false; error = "set-visibility: empty deviceId" }
    }
    try {
        $hr = [NativeHelpers]::SetEndpointVisibility($deviceId, $visible)
        if ($hr -ne 0) {
            return @{ ok = $false; error = "SetEndpointVisibility hr=0x$([int]$hr.ToString('X8'))"; hr = $hr }
        }
        return @{ ok = $true; deviceId = $deviceId; visible = $visible }
    } catch {
        return @{ ok = $false; error = "set-visibility exception: $_" }
    }
}

# ── probe: choose the silent-target method for this machine ──────────────────
# LISTENER-SAFE design (no device disabling — disabling changes the system default and
# kills the Electron getUserMedia stream that the AI listens through).
# The ONLY silent ACTIVE capture endpoint that exists driverlessly is a virtual-audio cable
# (CABLE Output / VoiceMeeter Out / etc.) that nothing is currently feeding. If present, we
# redirect ONLY the meeting app's process there (per-process; the listener mic is untouched).
# If no virtual cable exists, return 'none' so the caller uses the hotkey method instead.
#   • redirect-cable — redirect meeting app to an existing, active virtual-cable capture endpoint.
#   • none           — no virtual cable → caller uses hotkey.
function Invoke-Probe([string]$listenerDeviceId, [string]$listenerName) {
    $enumResult = Invoke-Enumerate
    if (-not $enumResult.ok) {
        return @{ ok = $false; error = "probe: enumerate failed: $($enumResult.error)" }
    }
    $devices = $enumResult.devices

    # Virtual-cable capture endpoints are silent when nothing feeds their render side.
    $isCable = {
        param($d)
        return ($d.name -match 'cable output|vb-audio|voicemeeter|virtual')
    }

    # Prefer an ACTIVE virtual-cable capture endpoint (valid redirect target + silent).
    $cable = $devices | Where-Object {
        $_.state -eq 'active' -and (& $isCable $_)
    } | Select-Object -First 1
    if ($cable) {
        return @{ ok = $true; method = 'redirect-cable'; targetDeviceId = $cable.id;
                  targetName = $cable.name; needsDisable = $false; devices = $devices }
    }

    # No virtual cable present → caller uses the hotkey method (listener-safe, universal).
    return @{ ok = $true; method = 'none'; targetDeviceId = $null; needsDisable = $false; devices = $devices }
}

# ── send-keys command (parsing + SendInput done in C#) ───────────────────────
function Invoke-SendKeys([string]$combo) {
    try {
        $sent = [NativeHelpers]::SendKeyCombo($combo)
    } catch {
        return @{ ok = $false; error = "send-keys exception: $_" }
    }
    if ($sent -eq 0) {
        return @{ ok = $false; error = "SendKeyCombo failed (parse or SendInput returned 0) for combo: $combo" }
    }
    return @{ ok = $true; sent = [int]$sent; combo = $combo }
}

# ── Server loop ───────────────────────────────────────────────────────────────
# Signal ready
[Console]::WriteLine((@{ ok = $true; ready = $true } | ConvertTo-Json -Compress))

while ($true) {
    $line = $null
    try { $line = [Console]::ReadLine() } catch { break }
    if ($null -eq $line) { break }
    $line = $line.Trim()
    if ($line -eq '') { continue }

    $response = $null
    try {
        $cmd = $line | ConvertFrom-Json

        switch ($cmd.cmd) {
            'init' {
                # Pre-warm the policy config + device enumerator (all inside C#)
                $ver = Initialize-Native
                $response = @{ ok = $true; policyVersion = $ver }
            }
            'enumerate' {
                $response = Invoke-Enumerate
            }
            'probe' {
                $response = Invoke-Probe $cmd.listenerDeviceId $cmd.listenerName
            }
            'set-visibility' {
                $response = Invoke-SetVisibility $cmd.deviceId ([int]$cmd.visible)
            }
            'pid-from-hwnd' {
                $response = Invoke-PidFromHwnd $cmd.hwnd
            }
            'redirect' {
                $response = Set-AudioEndpoint ([uint32]$cmd.pid) $cmd.deviceId
            }
            'restore' {
                # Pass null/empty deviceId to restore the OS default
                $response = Set-AudioEndpoint ([uint32]$cmd.pid) $null
            }
            'send-keys' {
                $response = Invoke-SendKeys $cmd.combo
            }
            'exit' {
                [Console]::WriteLine((@{ ok = $true; bye = $true } | ConvertTo-Json -Compress))
                exit 0
            }
            default {
                $response = @{ ok = $false; error = "Unknown command: $($cmd.cmd)" }
            }
        }
    } catch {
        $response = @{ ok = $false; error = "Handler exception: $_" }
    }

    if ($null -eq $response) { $response = @{ ok = $false; error = "null response" } }
    [Console]::WriteLine(($response | ConvertTo-Json -Compress -Depth 10))
}
