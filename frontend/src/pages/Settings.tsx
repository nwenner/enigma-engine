import { useState, useRef } from "react";
import { useSettings, useUpdateSettings, useTestConnection, useUploadKey } from "../api/hooks";
import type { MachineSettings } from "../api/types";

type Machine = "pc" | "deck";

export default function Settings() {
  const { data: settings, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();
  const testConn = useTestConnection();
  const uploadKey = useUploadKey();

  const [pcForm, setPcForm] = useState<Partial<MachineSettings> | null>(null);
  const [deckForm, setDeckForm] = useState<Partial<MachineSettings> | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error" | "info"; msg: string } | null>(null);

  const showToast = (type: "success" | "error" | "info", msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const getForm = (machine: Machine) =>
    machine === "pc" ? pcForm : deckForm;

  const setForm = (machine: Machine, patch: Partial<MachineSettings>) => {
    const setter = machine === "pc" ? setPcForm : setDeckForm;
    const current = getForm(machine) ?? (settings?.[machine] ?? {});
    setter({ ...current, ...patch });
  };

  const getValue = (machine: Machine, key: keyof MachineSettings) =>
    (getForm(machine) ?? settings?.[machine])?.[key];

  const handleSave = async () => {
    const body: { pc?: Partial<MachineSettings>; deck?: Partial<MachineSettings> } = {};
    if (pcForm) body.pc = pcForm;
    if (deckForm) body.deck = deckForm;
    try {
      await updateSettings.mutateAsync(body);
      setPcForm(null);
      setDeckForm(null);
      showToast("success", "Settings saved");
    } catch {
      showToast("error", "Failed to save settings");
    }
  };

  const handleTest = async (machine: Machine) => {
    // Save unsaved changes first
    const form = getForm(machine);
    if (form) {
      try {
        await updateSettings.mutateAsync({ [machine]: form });
      } catch {
        // continue anyway
      }
    }
    const result = await testConn.mutateAsync(machine);
    showToast(result.success ? "success" : "error", result.message);
  };

  const isDirty = pcForm !== null || deckForm !== null;

  if (isLoading) {
    return <div className="p-6 text-amber-700">Loading settings...</div>;
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-d2gold mb-6">Settings</h1>

      {toast && (
        <div
          className={`mb-4 p-3 rounded border text-sm ${
            toast.type === "success"
              ? "bg-green-950/50 border-green-800 text-green-300"
              : toast.type === "error"
              ? "bg-red-950/50 border-red-800 text-red-300"
              : "bg-blue-950/50 border-blue-800 text-blue-300"
          }`}
        >
          {toast.msg}
        </div>
      )}

      <div className="space-y-6">
        <MachineForm
          machine="pc"
          label="Windows PC"
          icon="🖥️"
          getValue={getValue}
          setForm={setForm}
          onTest={handleTest}
          testLoading={testConn.isPending}
          uploadKey={uploadKey}
        />
        <MachineForm
          machine="deck"
          label="Steam Deck"
          icon="🎮"
          getValue={getValue}
          setForm={setForm}
          onTest={handleTest}
          testLoading={testConn.isPending}
          uploadKey={uploadKey}
        />
      </div>

      {isDirty && (
        <div className="mt-6 flex gap-3 justify-end">
          <button
            onClick={() => { setPcForm(null); setDeckForm(null); }}
            className="px-4 py-2 border border-d2bg-border text-amber-400 rounded text-sm hover:bg-d2bg-elevated transition-colors"
          >
            Discard
          </button>
          <button
            onClick={handleSave}
            disabled={updateSettings.isPending}
            className="px-4 py-2 bg-d2gold hover:bg-d2gold-light text-d2bg font-bold rounded text-sm transition-colors disabled:opacity-50"
          >
            Save Changes
          </button>
        </div>
      )}
    </div>
  );
}

interface FormProps {
  machine: Machine;
  label: string;
  icon: string;
  getValue: (m: Machine, k: keyof MachineSettings) => unknown;
  setForm: (m: Machine, p: Partial<MachineSettings>) => void;
  onTest: (m: Machine) => void;
  testLoading: boolean;
  uploadKey: ReturnType<typeof useUploadKey>;
}

function MachineForm({ machine, label, icon, getValue, setForm, onTest, testLoading, uploadKey }: FormProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const authType = (getValue(machine, "auth_type") as string) || "password";
  const keyUploaded = getValue(machine, "key_uploaded") as boolean;

  const field = (key: keyof MachineSettings, label: string, type = "text", placeholder = "") => (
    <div>
      <label className="block text-xs text-amber-600 mb-1">{label}</label>
      <input
        type={type}
        placeholder={placeholder}
        value={(getValue(machine, key) as string) ?? ""}
        onChange={(e) => setForm(machine, { [key]: type === "number" ? Number(e.target.value) : e.target.value })}
        className="w-full bg-d2bg border border-d2bg-border rounded px-3 py-1.5 text-sm text-amber-100 placeholder-amber-800 focus:outline-none focus:border-d2gold"
      />
    </div>
  );

  const handleKeyFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await uploadKey.mutateAsync({ machine, file });
    } catch {
      // handled via toast at parent level
    }
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="bg-d2bg-surface border border-d2bg-border rounded-lg p-5">
      <h2 className="text-d2gold font-semibold mb-4 flex items-center gap-2">
        <span>{icon}</span> {label}
      </h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {field("host", "Hostname / IP", "text", "192.168.1.100")}
        <div>
          <label className="block text-xs text-amber-600 mb-1">Port</label>
          <input
            type="number"
            value={(getValue(machine, "port") as number) ?? 22}
            onChange={(e) => setForm(machine, { port: Number(e.target.value) })}
            className="w-full bg-d2bg border border-d2bg-border rounded px-3 py-1.5 text-sm text-amber-100 focus:outline-none focus:border-d2gold"
          />
        </div>
        {field("username", "SSH Username", "text", "user")}
        {field("save_path", "Save File Path", "text",
          machine === "pc"
            ? "C:/Users/YourName/Saved Games/Diablo II Resurrected"
            : "/home/deck/.steam/steam/userdata/.../remote"
        )}

        {/* Auth type toggle */}
        <div className="sm:col-span-2">
          <label className="block text-xs text-amber-600 mb-1">Authentication</label>
          <div className="flex gap-2">
            {(["password", "key"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setForm(machine, { auth_type: t })}
                className={`px-3 py-1.5 text-sm rounded transition-colors border ${
                  authType === t
                    ? "bg-d2gold text-d2bg font-bold border-d2gold"
                    : "bg-d2bg-elevated text-amber-400 border-d2bg-border hover:border-d2gold/50"
                }`}
              >
                {t === "password" ? "Password" : "SSH Key"}
              </button>
            ))}
          </div>
        </div>

        {authType === "password" && (
          <div className="sm:col-span-2">
            {field("password", "Password", "password", "••••••••")}
          </div>
        )}

        {authType === "key" && (
          <div className="sm:col-span-2">
            <label className="block text-xs text-amber-600 mb-1">SSH Private Key</label>
            <div className="flex items-center gap-3">
              <button
                onClick={() => fileRef.current?.click()}
                disabled={uploadKey.isPending}
                className="px-3 py-1.5 text-sm bg-d2bg-elevated border border-d2bg-border text-amber-300 rounded hover:border-d2gold/50 transition-colors disabled:opacity-50"
              >
                {uploadKey.isPending ? "Uploading..." : "Upload .pem / id_rsa"}
              </button>
              {keyUploaded && (
                <span className="text-green-400 text-xs">✓ Key uploaded</span>
              )}
              {!keyUploaded && (
                <span className="text-amber-700 text-xs">No key uploaded</span>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              accept=".pem,.key,.rsa,*"
              onChange={handleKeyFile}
            />
          </div>
        )}
      </div>

      <div className="mt-4 flex justify-end">
        <button
          onClick={() => onTest(machine)}
          disabled={testLoading}
          className="px-4 py-2 text-sm border border-d2gold/40 text-d2gold hover:bg-d2gold/10 rounded transition-colors disabled:opacity-50"
        >
          {testLoading ? "Testing..." : "Test Connection"}
        </button>
      </div>
    </div>
  );
}
