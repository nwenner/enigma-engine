# Enigma Engine ⚔️

Sync your Diablo 2 Resurrected save files between your Windows PC and Steam Deck — no USB drives, no manual copying. Enigma Engine runs a small web app on your home network that lets you push saves between machines with one click.

---

## What You Need

- A **Windows PC** running Diablo 2 Resurrected
- A **Steam Deck** running Diablo 2 Resurrected (via Steam or Battle.net/Proton)
- A **Mac, PC, or always-on machine** to run the Enigma Engine server (it just needs to be on the same Wi-Fi/network as your PC and Deck)
- All three devices on the **same home network**
- Python 3.9 or newer on the machine running the server

---

## One-Time Setup

### Step 1 — Enable SSH on your Windows PC

SSH is how the app talks to your machines. You only need to do this once.

1. Click the **Start menu**, search for **PowerShell**, right-click it and choose **Run as Administrator**
2. Paste in the following commands one at a time and hit Enter after each:

```
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

3. Find your PC's local IP address — run this and look for the **IPv4 Address** line:
```
ipconfig
```
It'll look something like `192.168.1.105`. Write it down.

---

### Step 2 — Enable SSH on your Steam Deck

1. Press the **Steam button** and go to **Power → Switch to Desktop**
2. Open **Konsole** (the terminal app — find it in the app menu)
3. Set a password if you haven't already (you'll use this to log into the app):
```
passwd
```
4. Enable SSH:
```
sudo systemctl enable --now sshd
```
5. Find your Deck's IP address:
```
ip addr show | grep "inet " | grep -v 127.0.0.1
```
Write down the IP — it'll look something like `192.168.1.42`.

---

### Step 3 — Find your save file paths

**Windows PC:**

Your saves are at:
```
C:/Users/YourName/Saved Games/Diablo II Resurrected
```
Replace `YourName` with your actual Windows username (the folder name under `C:\Users\`).

**Steam Deck (installed via Steam):**

Open Konsole and run:
```
find ~/.steam/steam/userdata -name "*.d2s" 2>/dev/null
```
Copy everything up to but not including the filename. For example if it shows `/home/deck/.steam/steam/userdata/123456/remote/MySave.d2s`, your path is `/home/deck/.steam/steam/userdata/123456/remote`.

**Steam Deck (installed via Battle.net/Proton):**

Run:
```
find ~/.local/share/Steam/steamapps/compatdata -name "*.d2s" 2>/dev/null
```
Same idea — copy everything before the filename.

---

### Step 4 — Download and run Enigma Engine

On the machine that will host the server (your Mac, for example):

1. Download or clone this repository
2. Open a terminal in the `enigma-engine` folder
3. Run:
```
./start.sh
```

The first time you run this it will take a minute to install dependencies. When you see:

```
Starting Enigma Engine → http://localhost:8080
```

Open **http://localhost:8080** in your browser.

> **Note:** If the machine running the server is not the one you're browsing from, replace `localhost` with that machine's IP address, e.g. `http://192.168.1.200:8080`.

---

### Step 5 — Configure the app

1. Click **Settings** in the sidebar
2. Fill in the **Windows PC** section:
   - **Hostname / IP:** the IP you found in Step 1
   - **Port:** `22`
   - **Username:** your Windows username
   - **Password:** your Windows login password
   - **Save path:** `C:/Users/YourName/Saved Games/Diablo II Resurrected`
   - **Authentication:** Password
3. Fill in the **Steam Deck** section:
   - **Hostname / IP:** the IP you found in Step 2
   - **Port:** `22`
   - **Username:** `deck`
   - **Password:** the password you set in Step 2
   - **Save path:** the path you found in Step 3
   - **Authentication:** Password
4. Click **Test Connection** for each machine — both should say "Connection successful"
5. Click **Save Changes**

---

## Syncing Your Saves

1. Open **http://localhost:8080** in your browser
2. Go to the **Dashboard** — your characters should appear in both panels
3. **Close Diablo 2 Resurrected on both machines** before syncing
4. Click **PC → Steam Deck** or **Steam Deck → PC** depending on which save you want to copy
5. A progress window will appear and update automatically — wait for it to say "Sync complete!"

That's it. Your saves are now in sync.

> ⚠️ Always close D2R before syncing. The app checks for this automatically and will warn you if the game is still running, but it's good habit.

---

## Backups

Every time you sync, the app automatically backs up the destination machine's saves before overwriting them. You can view and restore these backups from the **Backups** page.

By default the last 10 backups are kept. Older ones are pruned automatically.

---

## Sync History

The **History** page shows a log of every sync — when it happened, which direction, which files were transferred, and whether it succeeded.

---

## Keeping the Server Running

The server only needs to be running when you want to sync. Just run `./start.sh` when you need it and close the terminal when you're done.

If you want it to always be available, you can leave the terminal window open, or look into setting it up as a background service for your OS.

---

## Troubleshooting

**"Connection failed" on Windows**
- Make sure the OpenSSH Server service is running: search for **Services** in the Start menu, find **OpenSSH SSH Server**, and check that its status is **Running**
- Double check your Windows password — if you use a PIN to log in, the SSH password is your separate account password (Settings → Accounts → Sign-in options → Password)
- Make sure your PC's IP hasn't changed — check `ipconfig` again and update the app if it has. Setting a static IP in your router settings prevents this.

**"Connection failed" on Steam Deck**
- SSH doesn't survive reboots unless you enabled it — go back to Desktop Mode and run `sudo systemctl enable --now sshd` again
- Make sure the Deck is on Wi-Fi, not in airplane mode

**Characters not showing up**
- Double-check the save path — it must be the directory, not a filename
- Make sure D2R has been launched at least once on that machine so save files exist

**"D2R is running" warning**
- Close the game completely on both machines, not just minimized
- On PC, check Task Manager to confirm `D2R.exe` is not running

**The app won't start**
- Make sure you have Python 3.9 or newer: run `python3 --version` in your terminal
- Try deleting the `.venv` folder and running `./start.sh` again to reinstall dependencies
