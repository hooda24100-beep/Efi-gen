import subprocess, platform, json, requests, zipfile
import os, shutil, datetime
from pathlib import Path

# ════════════════════════════
# TOOL: HARDWARE SCANNER
# ════════════════════════════

def scan_hardware():
    hw = {}
    if platform.system() == "Windows":
        def wmic(q):
            r = subprocess.run(["wmic"] + q.split() + ["get", "/format:list"],
                capture_output=True, text=True)
            return r.stdout.strip()

        hw["cpu"] = wmic("cpu")
        hw["gpu"] = wmic("path win32_VideoController")
        hw["audio"] = wmic("path win32_SoundDevice")
        hw["network"] = wmic("path win32_NetworkAdapter")
        hw["storage"] = wmic("diskdrive")
        hw["bios"] = wmic("bios")
        hw["baseboard"] = wmic("baseboard")

    elif platform.system() == "Linux":
        hw["pci"] = subprocess.run(["lspci", "-v"],
            capture_output=True, text=True).stdout
        hw["cpu"] = open("/proc/cpuinfo").read()
        hw["dmi"] = subprocess.run(["dmidecode"],
            capture_output=True, text=True).stdout

    return json.dumps(hw)

# ════════════════════════════
# TOOL: KEXT FETCHER
# ════════════════════════════

KEXT_REPOS = {
    "Lilu":                 "acidanthera/Lilu",
    "VirtualSMC":           "acidanthera/VirtualSMC",
    "WhateverGreen":        "acidanthera/WhateverGreen",
    "AppleALC":             "acidanthera/AppleALC",
    "NVMeFix":              "acidanthera/NVMeFix",
    "RestrictEvents":       "acidanthera/RestrictEvents",
    "FeatureUnlock":        "acidanthera/FeatureUnlock",
    "CPUFriend":            "acidanthera/CPUFriend",
    "AirportItlwm":         "OpenIntelWireless/itlwm",
    "IntelBluetoothFirmware":"OpenIntelWireless/IntelBluetoothFirmware",
    "VoodooI2C":            "VoodooI2C/VoodooI2C",
    "VoodooPS2Controller":  "acidanthera/VoodooPS2",
    "RealtekRTL8111":       "Mieze/RTL8111_driver_for_OS_X",
    "LucyRTL8125":          "Mieze/LucyRTL8125Ethernet",
    "IntelMausi":           "acidanthera/IntelMausi",
    "ECEnabler":            "1Revenger1/ECEnabler",
    "BrightnessKeys":       "acidanthera/BrightnessKeys",
}

def get_latest_kext(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    r = requests.get(url, headers={"Accept": "application/vnd.github+json"})
    data = r.json()
    return data["tag_name"], data["assets"]

def fetch_kext(name, output_dir):
    if name not in KEXT_REPOS:
        return f"UNKNOWN_KEXT: {name}"
    repo = KEXT_REPOS[name]
    version, assets = get_latest_kext(repo)
    for asset in assets:
        if asset["name"].endswith(".zip"):
            r = requests.get(asset["browser_download_url"])
            zip_path = Path(output_dir) / asset["name"]
            zip_path.write_bytes(r.content)
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(output_dir)
            zip_path.unlink()
            return f"FETCHED: {name} {version}"
    return f"NO_ZIP_FOUND: {name}"

# ════════════════════════════
# TOOL: EFI BUILDER
# ════════════════════════════

def write_efi(config_plist: str, kext_list: list,
              ssdt_list: list, base_path="./EFI-OUTPUT"):
    dirs = [
        "EFI/BOOT",
        "EFI/OC/ACPI",
        "EFI/OC/Drivers",
        "EFI/OC/Kexts",
        "EFI/OC/Resources",
        "EFI/OC/Tools",
    ]
    for d in dirs:
        Path(f"{base_path}/{d}").mkdir(parents=True, exist_ok=True)

    Path(f"{base_path}/EFI/OC/config.plist").write_text(config_plist)

    kext_dir = f"{base_path}/EFI/OC/Kexts"
    for kext in kext_list:
        fetch_kext(kext, kext_dir)

    return f"EFI structure built at {base_path}"

# ════════════════════════════
# TOOL: PACKAGER
# ════════════════════════════

def package_efi(base_path="./EFI-OUTPUT"):
    cpu = platform.processor().replace(" ", "_")[:20]
    date = datetime.date.today().isoformat()
    zip_name = f"EFI-GPT_{cpu}_{date}"
    shutil.make_archive(zip_name, "zip", base_path)
    return f"DELIVERED: {zip_name}.zip"

# ════════════════════════════
# AGENT RUNNER
# ════════════════════════════

def run_agent():
    import anthropic  # pip install anthropic

    client = anthropic.Anthropic(api_key="YOUR_API_KEY")

    print("[EFI-GPT] Scanning hardware...")
    hardware_data = scan_hardware()

    tools = [
        {
            "name": "scan_hardware",
            "description": "Scans system hardware and returns JSON",
            "input_schema": {"type": "object", "properties": {}}
        },
        {
            "name": "fetch_kext",
            "description": "Downloads a kext by name to output dir",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "output_dir": {"type": "string"}
                },
                "required": ["name", "output_dir"]
            }
        },
        {
            "name": "write_efi",
            "description": "Assembles full EFI folder structure",
            "input_schema": {
                "type": "object",
                "properties": {
                    "config_plist": {"type": "string"},
                    "kext_list": {"type": "array",
                                  "items": {"type": "string"}},
                    "ssdt_list": {"type": "array",
                                  "items": {"type": "string"}}
                },
                "required": ["config_plist", "kext_list", "ssdt_list"]
            }
        },
        {
            "name": "package_efi",
            "description": "Zips and delivers final EFI",
            "input_schema": {"type": "object", "properties": {}}
        }
    ]

    messages = [{
        "role": "user",
        "content": f"Hardware scan complete. Begin autonomous EFI generation.\n\n{hardware_data}"
    }]

    # AGENT LOOP
    while True:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=8000,
            system=SYSTEM_PROMPT,  # paste Part 1 here as string
            tools=tools,
            messages=messages
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            print("[EFI-GPT] DONE.")
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"[EFI-GPT] Calling: {block.name}")
                if block.name == "scan_hardware":
                    result = scan_hardware()
                elif block.name == "fetch_kext":
                    result = fetch_kext(block.input["name"],
                                        block.input.get("output_dir",
                                        "./EFI-OUTPUT/EFI/OC/Kexts"))
                elif block.name == "write_efi":
                    result = write_efi(block.input["config_plist"],
                                       block.input["kext_list"],
                                       block.input["ssdt_list"])
                elif block.name == "package_efi":
                    result = package_efi()
                else:
                    result = "UNKNOWN TOOL"

                print(f"[EFI-GPT] Result: {result}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result)
                })

        messages.append({"role": "user", "content": tool_results})

if __name__ == "__main__":
    run_agent()
