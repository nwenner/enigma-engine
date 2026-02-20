import { useState, useRef } from "react";
import {
  useSettings,
  useUpdateSettings,
  useTestConnection,
  useUploadKey,
  useAutoSyncStatus,
  useUpdateAutoSyncConfig,
  useNotificationConfig,
  useUpdateNotificationConfig,
  useTestNotification,
} from "../api/hooks";
import InfoModal from "../components/InfoModal";
import type { MachineSettings, NotificationConfig } from "../api/types";

type Machine = "pc" | "deck";

const POLL_INTERVAL_OPTIONS = [
  { label: "15 seconds", value: 15 },
  { label: "30 seconds (default)", value: 30 },
  { label: "60 seconds", value: 60 },
  { label: "2 minutes", value: 120 },
];

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

  const getForm = (machine: Machine) => machine === "pc" ? pcForm : deckForm;
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
    const form = getForm(machine);
    if (form) {
      try { await updateSettings.mutateAsync({ [machine]: form }); } catch { /* continue */ }
    }
    const result = await testConn.mutateAsync(machine);
    showToast(result.success ? "success" : "error", result.message);
  };

  const isDirty = pcForm !== null || deckForm !== null;

  if (isLoading) {
    return <div className="p-6 text-slate-500">Loading settings...</div>;
  }

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto animate-fadeIn">
      <div className="mb-7">
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Settings</h1>
      </div>

      {toast && (
        <div
          className={`mb-5 p-3 border text-sm animate-fadeIn ${
            toast.type === "success"
              ? "bg-green-950/30 border-green-800/50 text-green-400"
              : toast.type === "error"
              ? "bg-red-950/30 border-red-800/50 text-red-400"
              : "bg-blue-950/30 border-blue-800/50 text-blue-400"
          }`}
        >
          {toast.msg}
        </div>
      )}

      <div className="space-y-5">
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

        {/* Notifications */}
        <NotificationsForm />

        {/* Auto-Sync */}
        <AutoSyncSection />
      </div>

      {isDirty && (
        <div className="mt-6 flex gap-3 justify-end">
          <button
            onClick={() => { setPcForm(null); setDeckForm(null); }}
            className="btn-d2-ghost"
          >
            Discard
          </button>
          <button
            onClick={handleSave}
            disabled={updateSettings.isPending}
            className="btn-d2-filled"
          >
            Save Changes
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Notifications ────────────────────────────────────────────────────────────

const EMPTY_CONFIG: NotificationConfig = {
  type: "none",
  aws_profile: "",
  aws_region: "us-east-1",
  ses_from: "",
  ses_to: "",
};

function NotificationsForm() {
  const { data: saved } = useNotificationConfig();
  const updateConfig = useUpdateNotificationConfig();
  const testNotification = useTestNotification();
  const [form, setForm] = useState<NotificationConfig | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  const showToast = (type: "success" | "error", msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const current: NotificationConfig = form ?? saved ?? EMPTY_CONFIG;
  const isDirty = form !== null;

  const handleSave = async () => {
    try {
      await updateConfig.mutateAsync(current);
      setForm(null);
      showToast("success", "Notification settings saved");
    } catch {
      showToast("error", "Failed to save notification settings");
    }
  };

  const handleTest = async () => {
    // Save first if dirty so the test uses the latest values
    if (isDirty) {
      try { await updateConfig.mutateAsync(current); setForm(null); } catch { /* fall through to test anyway */ }
    }
    const result = await testNotification.mutateAsync();
    showToast(result.success ? "success" : "error", result.message);
  };

  const [showInfo, setShowInfo] = useState(false);

  return (
    <div className="card-d2 p-5">
      <h2 className="font-diablo text-d2gold text-sm tracking-widest mb-1 flex items-center gap-2">
        <span>🔔</span> Notifications
        <button
          onClick={() => setShowInfo(true)}
          className="ml-auto text-[10px] text-slate-600 hover:text-slate-300 border border-slate-700 hover:border-slate-500 w-5 h-5 flex items-center justify-center transition-colors shrink-0"
          title="Help"
        >
          ?
        </button>
      </h2>
      <p className="text-slate-500 text-xs mb-5 leading-relaxed">
        Receive a notification when an auto-sync conflict is detected.
      </p>

      {showInfo && (
        <InfoModal title="Notifications — Amazon SES" onClose={() => setShowInfo(false)}>
          <p>
            Enigma Engine can send you an email when an auto-sync conflict is detected —
            meaning both machines have new saves and the app can't automatically decide
            which to keep.
          </p>
          <p className="text-slate-500 text-xs mt-1">
            This requires an AWS account with Amazon Simple Email Service (SES) configured.
          </p>
          <div className="space-y-2.5 mt-1">
            <HelpRow term="AWS Profile">
              The profile name in your AWS credentials file
              (<code className="text-d2gold/80 bg-d2bg px-1">~/.aws/credentials</code>).
              Usually <strong className="text-slate-200">default</strong>. The credentials
              file must be mounted into the Docker container — see the project README.
            </HelpRow>
            <HelpRow term="AWS Region">
              The region where your SES is set up, e.g.{" "}
              <strong className="text-slate-200">us-east-1</strong> or{" "}
              <strong className="text-slate-200">eu-west-1</strong>. Find it in the AWS
              Console under SES.
            </HelpRow>
            <HelpRow term="From / To Address">
              The email addresses for sending and receiving notifications. If your SES
              account is still in <em>sandbox mode</em>, both addresses must be individually
              verified in the AWS Console (SES → Verified identities) before emails will
              be delivered.
            </HelpRow>
          </div>
        </InfoModal>
      )}

      {toast && (
        <div
          className={`mb-4 p-3 border text-sm animate-fadeIn ${
            toast.type === "success"
              ? "bg-green-950/30 border-green-800/50 text-green-400"
              : "bg-red-950/30 border-red-800/50 text-red-400"
          }`}
        >
          {toast.msg}
        </div>
      )}

      <div className="space-y-4">
        {/* Type selector */}
        <div>
          <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">Type</label>
          <select
            value={current.type}
            onChange={(e) => setForm({ ...current, type: e.target.value as NotificationConfig["type"] })}
            className="bg-d2bg border border-d2bg-border px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-d2gold/50 transition-colors"
          >
            <option value="none">None</option>
            <option value="ses">Amazon SES (Email)</option>
          </select>
        </div>

        {current.type === "ses" && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
            <div>
              <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">AWS Profile</label>
              <input
                type="text"
                placeholder="default"
                value={current.aws_profile}
                onChange={(e) => setForm({ ...current, aws_profile: e.target.value })}
                className="input-d2"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">AWS Region</label>
              <input
                type="text"
                placeholder="us-east-1"
                value={current.aws_region}
                onChange={(e) => setForm({ ...current, aws_region: e.target.value })}
                className="input-d2"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">From Address</label>
              <input
                type="email"
                placeholder="you@example.com"
                value={current.ses_from}
                onChange={(e) => setForm({ ...current, ses_from: e.target.value })}
                className="input-d2"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">To Address</label>
              <input
                type="email"
                placeholder="you@example.com"
                value={current.ses_to}
                onChange={(e) => setForm({ ...current, ses_to: e.target.value })}
                className="input-d2"
              />
            </div>
          </div>
        )}
      </div>

      <div className="mt-5 flex gap-2 justify-end">
        {isDirty && (
          <button
            onClick={() => setForm(null)}
            className="btn-d2-ghost text-xs px-3 py-1.5"
          >
            Discard
          </button>
        )}
        {isDirty && (
          <button
            onClick={handleSave}
            disabled={updateConfig.isPending}
            className="btn-d2-filled text-xs px-3 py-1.5"
          >
            {updateConfig.isPending ? "Saving..." : "Save"}
          </button>
        )}
        {current.type !== "none" && (
          <button
            onClick={handleTest}
            disabled={testNotification.isPending || updateConfig.isPending}
            className="btn-d2 text-xs px-3 py-1.5"
          >
            {testNotification.isPending ? "Sending..." : "Send Test"}
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Machine Form ─────────────────────────────────────────────────────────────

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

  const field = (key: keyof MachineSettings, fieldLabel: string, type = "text", placeholder = "") => (
    <div>
      <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">{fieldLabel}</label>
      <input
        type={type}
        placeholder={placeholder}
        value={(getValue(machine, key) as string) ?? ""}
        onChange={(e) => setForm(machine, { [key]: type === "number" ? Number(e.target.value) : e.target.value })}
        className="input-d2"
      />
    </div>
  );

  const handleKeyFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try { await uploadKey.mutateAsync({ machine, file }); } catch { /* handled */ }
    if (fileRef.current) fileRef.current.value = "";
  };

  const [showInfo, setShowInfo] = useState(false);

  return (
    <div className="card-d2 p-5">
      <h2 className="font-diablo text-d2gold text-sm tracking-widest mb-5 flex items-center gap-2">
        <span>{icon}</span> {label}
        <button
          onClick={() => setShowInfo(true)}
          className="ml-auto text-[10px] text-slate-600 hover:text-slate-300 border border-slate-700 hover:border-slate-500 w-5 h-5 flex items-center justify-center transition-colors shrink-0"
          title="Help"
        >
          ?
        </button>
      </h2>

      {showInfo && (
        <InfoModal title={`${label} — SSH Connection`} onClose={() => setShowInfo(false)}>
          <p>
            Enigma Engine connects to your <strong className="text-slate-200">{label}</strong> over
            SSH (Secure Shell) to read and write Diablo II Resurrected save files remotely.
            Both machines must be on the same local network.
          </p>
          <div className="space-y-2.5 mt-1">
            <HelpRow term="Hostname / IP">
              The local network address of your {label}.{" "}
              {machine === "pc" ? (
                <>Open <em>Command Prompt</em> and type <code className="text-d2gold/80 bg-d2bg px-1">ipconfig</code> — look for "IPv4 Address" under your Wi-Fi or Ethernet adapter.</>
              ) : (
                <>Go to <em>Settings → Internet</em>, tap your Wi-Fi network, and look for "IP address".</>
              )}
            </HelpRow>
            <HelpRow term="Port">
              The SSH port — leave this as <strong className="text-slate-200">22</strong> unless
              you have specifically changed it on that machine.
            </HelpRow>
            <HelpRow term="SSH Username">
              {machine === "pc" ? (
                <>Your Windows account name. Find it in <em>Settings → Accounts</em>.</>
              ) : (
                <>Always <strong className="text-slate-200">deck</strong> on Steam Deck.</>
              )}
            </HelpRow>
            <HelpRow term="Save File Path">
              {machine === "pc" ? (
                <>Typically <code className="text-d2gold/80 bg-d2bg px-1 text-[11px]">C:/Users/YourName/Saved Games/Diablo II Resurrected</code>. Replace "YourName" with your Windows username.</>
              ) : (
                <>Typically <code className="text-d2gold/80 bg-d2bg px-1 text-[11px]">/home/deck/.steam/steam/userdata/[SteamID]/219700/remote</code>. Replace [SteamID] with your numeric Steam ID (the folder inside userdata).</>
              )}
            </HelpRow>
            <HelpRow term="Authentication">
              <strong className="text-slate-200">Password</strong> — enter the machine's login
              password. Simple but the password is stored encrypted in the app database.{" "}
              <strong className="text-slate-200">SSH Key</strong> — more secure. Generate a key
              pair, place the public key in <code className="text-d2gold/80 bg-d2bg px-1">~/.ssh/authorized_keys</code> on
              the target machine, then upload the private key (.pem / id_rsa) here.
            </HelpRow>
          </div>
        </InfoModal>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {field("host", "Hostname / IP", "text", "192.168.1.100")}
        <div>
          <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">Port</label>
          <input
            type="number"
            value={(getValue(machine, "port") as number) ?? 22}
            onChange={(e) => setForm(machine, { port: Number(e.target.value) })}
            className="input-d2"
          />
        </div>
        {field("username", "SSH Username", "text", "user")}
        {field("save_path", "Save File Path", "text",
          machine === "pc"
            ? "C:/Users/YourName/Saved Games/Diablo II Resurrected"
            : "/home/deck/.steam/steam/userdata/.../remote"
        )}

        {/* Auth type */}
        <div className="sm:col-span-2">
          <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">Authentication</label>
          <div className="flex gap-2">
            {(["password", "key"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setForm(machine, { auth_type: t })}
                className={`px-3 py-1.5 text-sm transition-all duration-150 border ${
                  authType === t
                    ? "bg-d2gold/15 text-d2gold border-d2gold/50"
                    : "bg-d2bg-elevated text-slate-400 border-d2bg-border hover:border-slate-600 hover:text-slate-200"
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
            <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">SSH Private Key</label>
            <div className="flex items-center gap-3">
              <button
                onClick={() => fileRef.current?.click()}
                disabled={uploadKey.isPending}
                className="btn-d2-ghost text-sm"
              >
                {uploadKey.isPending ? "Uploading..." : "Upload .pem / id_rsa"}
              </button>
              {keyUploaded ? (
                <span className="text-green-400 text-xs flex items-center gap-1">
                  <span>✓</span> Key uploaded
                </span>
              ) : (
                <span className="text-slate-600 text-xs">No key uploaded</span>
              )}
            </div>
            <input ref={fileRef} type="file" className="hidden" accept=".pem,.key,.rsa,*" onChange={handleKeyFile} />
          </div>
        )}
      </div>

      <div className="mt-5 flex justify-end">
        <button
          onClick={() => onTest(machine)}
          disabled={testLoading}
          className="btn-d2"
        >
          {testLoading ? "Testing..." : "Test Connection"}
        </button>
      </div>
    </div>
  );
}

// ─── Auto-Sync Section ────────────────────────────────────────────────────────

function AutoSyncSection() {
  const { data: autoSync } = useAutoSyncStatus();
  const updateAutoSync = useUpdateAutoSyncConfig();
  const [showInfo, setShowInfo] = useState(false);

  return (
    <div className="card-d2 p-5">
      <h2 className="font-diablo text-d2gold text-sm tracking-widest mb-1 flex items-center gap-2">
        <span>🔄</span> Auto-Sync
        <button
          onClick={() => setShowInfo(true)}
          className="ml-auto text-[10px] text-slate-600 hover:text-slate-300 border border-slate-700 hover:border-slate-500 w-5 h-5 flex items-center justify-center transition-colors shrink-0"
          title="Help"
        >
          ?
        </button>
      </h2>
      <p className="text-slate-500 text-xs mb-5 leading-relaxed">
        When enabled, automatically syncs saves when D2R closes. Both machines must be reachable.
      </p>

      {showInfo && (
        <InfoModal title="Auto-Sync" onClose={() => setShowInfo(false)}>
          <p>
            When enabled, Enigma Engine monitors both machines and automatically syncs your
            save files shortly after you close Diablo II Resurrected — no manual button
            press needed.
          </p>
          <div className="space-y-2.5 mt-1">
            <HelpRow term="How it works">
              The app polls both machines at the configured interval to check whether D2R
              is running. When it detects D2R has closed on one machine, it waits briefly
              and then syncs that machine's saves to the other.
            </HelpRow>
            <HelpRow term="Conflicts">
              If both machines have new saves since the last sync (e.g. you played on both
              before syncing), the app won't overwrite either — it flags a conflict on the
              Dashboard for you to resolve manually.
            </HelpRow>
            <HelpRow term="Offline machine">
              If the destination machine is offline when D2R closes, the saves are captured
              locally and pushed automatically when the destination comes back online.
            </HelpRow>
            <HelpRow term="Poll Interval">
              How often to check whether D2R is still running. Shorter intervals mean
              faster detection but slightly more network traffic. 30 seconds is a good
              default for most home networks.
            </HelpRow>
          </div>
        </InfoModal>
      )}

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-300">Enable auto-sync</span>
          <button
            onClick={() =>
              updateAutoSync.mutate({
                enabled: !(autoSync?.enabled ?? false),
                poll_interval_seconds: autoSync?.poll_interval ?? 30,
              })
            }
            disabled={updateAutoSync.isPending}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none disabled:opacity-50 ${
              autoSync?.enabled
                ? "bg-d2gold"
                : "bg-d2bg-elevated border border-d2bg-border"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 shadow-sm ${
                autoSync?.enabled ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">
            Poll interval
          </label>
          <select
            value={autoSync?.poll_interval ?? 30}
            onChange={(e) =>
              updateAutoSync.mutate({
                enabled: autoSync?.enabled ?? false,
                poll_interval_seconds: Number(e.target.value),
              })
            }
            disabled={updateAutoSync.isPending}
            className="bg-d2bg border border-d2bg-border px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-d2gold/50 disabled:opacity-50 transition-colors"
          >
            {POLL_INTERVAL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

// ─── Shared helpers ───────────────────────────────────────────────────────────

function HelpRow({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="border-l-2 border-d2bg-border pl-3">
      <p className="text-slate-300 text-xs font-medium mb-0.5">{term}</p>
      <p className="text-slate-500 text-xs leading-relaxed">{children}</p>
    </div>
  );
}
