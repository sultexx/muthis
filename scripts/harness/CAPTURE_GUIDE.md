# Capturing the four fixture screens, then starting the live run

The live run shows the model four fixed pictures of a screen instead of your real
screen. This guide makes those four pictures, then starts the run.

**Treat every pixel as public.** The pictures are sent to the model on every turn of
the run, and they may later be committed to the public repository. No personal file,
name, address, message or account may appear in any of them.

Follow each step exactly as written. **If your screen does not look the way a step
says, stop and tell Claude. Do not improvise.**

All commands are typed in **PowerShell**. Type each line exactly, then press Enter.

---

## Before you start (once)

1. Open PowerShell: press the Windows key, type `PowerShell`, press Enter.
2. Type these two lines:

   ```
   cd $HOME\Desktop\Muthis_v4.1
   $env:PYTHONIOENCODING = "utf-8"
   ```

3. Turn on **Do not disturb**, so that no notification can appear in a picture:
   Settings → System → Notifications → turn on "Do not disturb".
4. Hide the desktop icons: right-click an empty spot on the desktop → View → click
   "Show desktop icons" so that its tick disappears.
5. Use a plain background: Settings → Personalization → Background → next to
   "Personalize your background" choose "Solid color", then click any colour.
6. Look at the taskbar at the bottom of the screen. If it shows the name of a place
   (for example beside the weather), turn it off: Settings → Personalization →
   Taskbar → turn off "Widgets".
7. Close every window you do not need: browsers, e-mail, chat, File Explorer, open
   documents. Leave PowerShell open.

When all four pictures are done you may undo steps 3 to 6.

---

## How every capture works

The capture command waits **8 seconds**, then photographs your **main screen**,
whatever is on top at that moment.

1. Set the screen up exactly as that screen's section below says.
2. Click in PowerShell. Type the section's **capture command** and press Enter.
3. At once, bring the screen back:
   - for **screen 1 (`desktop`)**: press **Windows + D**;
   - for **screens 2, 3 and 4**: press **Alt + Tab once** — this returns to the window
     you set up just before clicking PowerShell.

   PowerShell must not be visible when the 8 seconds end. (If you have a second
   monitor, you may keep PowerShell there instead: only the main monitor is captured.)
4. Move the mouse to an empty spot, away from every button, so that no tooltip opens.
   Touch nothing until the 8 seconds have passed.
5. Go back to PowerShell. After the countdown the command prints four lines: `saved …`,
   `sha256 …`, **`sent at (1280, 720)`** and `Open the image and check it…`. If the
   `sent at` line shows any other numbers, or the command printed an error, stop and
   tell Claude.
6. Type the section's **open command**. The picture opens. Look at all of it, then zoom
   into its four corners and the taskbar. Check it against the section's two lists:
   **Must be visible** and **Must NOT be visible**.
7. If anything is wrong: fix the screen and run the **capture command** again. A new
   capture cancels the old one.
8. Only when the picture passes both lists: type the section's **review command**.
   It prints the screen's name followed by `reviewed at sha256 …`.

---

## Screen 1 of 4 — `desktop`

Used by S1, S1c, S3, S4, S5, S7 and S8: questions about a document, a web search,
Python, a small function and leap years. The picture is the empty desktop.

**Set up:** nothing to open. Steps 4 and 5 of "Before you start" have already hidden the
icons and set a plain background. In step 3 of "How every capture works", press
**Windows + D**.

**Must be visible**
- The plain background colour.
- The taskbar.

**Must NOT be visible**
- Any window.
- Any desktop icon, or any file or folder name.
- Any photo.
- The Start menu, or any notification.
- Any name, e-mail address or account picture.

**Capture command**
```
.venv\Scripts\python.exe scripts\harness\capture.py desktop
```

**Open command**
```
Invoke-Item scripts\harness\fixtures\screens\desktop.png
```

**Review command** (only after the picture passes both lists)
```
.venv\Scripts\python.exe scripts\harness\capture.py desktop --review
```

---

## Screen 2 of 4 — `editor_save`

Used by S2: «وين زر الحفظ؟» ("where is the save button?"). The model must point at a
button labelled **Save**, and its explanation is checked for that label, so the label
must be visible as text.

**Set up**
1. In PowerShell type `mspaint` and press Enter. Paint opens with an empty white canvas.
   If a pop-up or tip appears in Paint, close it with its X.
2. Press **Windows + Up arrow** so that Paint fills the screen.
3. Press the mouse button on the white canvas and drag a little, to draw one short line.
4. Press **Alt + F4**. Paint asks whether to save your changes and shows three buttons:
   **Save**, **Don't save** and **Cancel**. Leave this question open and click none of
   its buttons. (If Paint closed instead, start again from step 1.)
5. Click PowerShell, and continue with step 2 of "How every capture works". In its
   step 4, put the mouse over the white canvas, not over the question.

**Must be visible**
- Paint, filling the screen.
- The question, with a button labelled **Save** (or **حفظ** if Windows is in Arabic).
- The line on the canvas.

**Must NOT be visible**
- Any picture, initials or name of an account. Look at Paint's top-right corner.
- Any file name other than "Untitled".
- Any other window.

**Capture command**
```
.venv\Scripts\python.exe scripts\harness\capture.py editor_save
```

**Open command**
```
Invoke-Item scripts\harness\fixtures\screens\editor_save.png
```

**Review command** (only after the picture passes both lists)
```
.venv\Scripts\python.exe scripts\harness\capture.py editor_save --review
```

Afterwards, click **Don't save** in Paint to close it.

---

## Screen 3 of 4 — `editor_code`

Used by S6: «اشرح لي هذا الكود» ("explain this code"). The model must see the code
file with its line numbers and its path.

**Set up**
1. In PowerShell type this line and press Enter. VS Code opens this project and the
   file `explain_me.py`:

   ```
   code . scripts\harness\fixtures\explain_me.py
   ```

2. If more than one tab shows above the code: right-click the tab `explain_me.py` →
   "Close Others".
3. Hide what shows around the code. Each key below hides only what is showing; if you
   hide the wrong thing, press the same key again.
   - A file tree on the left: press **Ctrl + B**.
   - A terminal or panel at the bottom: press **Ctrl + J**.
   - A chat or any panel on the right: press **Ctrl + Alt + B**.
4. Press **Windows + Up arrow** so that VS Code fills the screen.
5. If a message box shows in the bottom-right corner, click its X.
6. Click PowerShell, and continue with step 2 of "How every capture works". In its
   step 4, put the mouse in the empty area below the code.

**Must be visible**
- VS Code, filling the screen.
- Exactly one tab: `explain_me.py`.
- All nine lines of the code, with their line numbers 1 to 9 on the left. An empty
  tenth line may show as well.
- Above the code, the path `scripts › harness › fixtures › explain_me.py`.

**Must NOT be visible**
- A terminal, a file tree or a chat.
- Any other file's tab.
- Any message box.
- The path of your user folder (anything beginning `C:\Users\`).
- Any name or account picture.

**Capture command**
```
.venv\Scripts\python.exe scripts\harness\capture.py editor_code
```

**Open command**
```
Invoke-Item scripts\harness\fixtures\screens\editor_code.png
```

**Review command** (only after the picture passes both lists)
```
.venv\Scripts\python.exe scripts\harness\capture.py editor_code --review
```

---

## Screen 4 of 4 — `notepad_text`

Used by S9: «علّمني أنسخ النص من المفكرة وألصقه في مستند جديد» ("teach me to copy the
text from Notepad and paste it into a new document").

**Set up**
1. In PowerShell type `notepad` and press Enter. Notepad opens.
2. In Notepad press **Ctrl + Shift + N**. A second Notepad window opens, with one empty
   tab named "Untitled". Do everything below in this **new** window. Leave any other
   Notepad window alone and do not close its tabs: they may hold notes you have not
   saved.
3. Press **Windows + Up arrow** so that the new window fills the screen.
4. Copy the three lines below (only the lines, not the marks around them) and paste
   them into the new window with **Ctrl + V**:

   ```
   الماء يغلي عند مئة درجة مئوية.
   في الأسبوع سبعة أيام.
   تشرق الشمس من الشرق.
   ```

5. Click once at the end of the last line, so that no text is highlighted.
6. Click PowerShell, and continue with step 2 of "How every capture works". In its
   step 4, put the mouse in the empty area below the text.

**Must be visible**
- The new Notepad window, filling the screen.
- Exactly one tab in its tab bar.
- The three lines, with no highlighted text.

**Must NOT be visible**
- Any other tab.
- Any file name other than "Untitled".
- Any picture, initials or name of an account. Look at the top-right corner.
- Any other window.

**Capture command**
```
.venv\Scripts\python.exe scripts\harness\capture.py notepad_text
```

**Open command**
```
Invoke-Item scripts\harness\fixtures\screens\notepad_text.png
```

**Review command** (only after the picture passes both lists)
```
.venv\Scripts\python.exe scripts\harness\capture.py notepad_text --review
```

Afterwards you may close the new Notepad window without saving.

---

## After all four screens

Check that the harness accepts all four pictures. This command does **not** start the
run:

```
.venv\Scripts\python.exe scripts\harness run --config scripts\harness\configs\A.json
```

It prints `REFUSED:` and a list of reasons under it. **None of the reasons may begin
with a screen's name** (`desktop`, `editor_save`, `editor_code`, `notepad_text`). These
reasons are expected at this point: `--live was not given` and
`--budget-usd is required` — and `docker info failed` if Docker Desktop is not running.

Do not commit anything. The pictures are ignored by git; Claude handles the rest in the
run session.

---

## The live run, in this order

**Before the run:** tell Claude your reading decision: read every passage, or a sample.
In the same session as the run, Claude writes that decision into the pre-registration,
together with the two notes DEC-155 found out of date, and commits it. Only then do you
type the commands below. Do not edit `prereg.json` yourself.

**Plan the day.** Start in the morning, Riyadh time. The spending cap counts per UTC
day, and a UTC day begins at 03:00 Riyadh time; both runs should finish before then.
Nothing has measured yet how long a run takes: allow several hours for each.

**Do not use the Mut'his app until the last command has finished.** The harness checks
that the app's log did not change during the run, and the app writes to that log.

In PowerShell, one line at a time:

1. Go to the project folder:
   ```
   cd $HOME\Desktop\Muthis_v4.1
   ```
2. Let Arabic text print:
   ```
   $env:PYTHONIOENCODING = "utf-8"
   ```
3. Start Docker Desktop and wait until it shows that the engine is running. Then:
   ```
   docker info
   ```
   It must print details with no line beginning with `ERROR`.
4. The self-test:
   ```
   .venv\Scripts\python.exe scripts\harness selftest
   ```
   Its last line must begin `X of X checks pass`, with both numbers the same.
5. The preflight:
   ```
   .venv\Scripts\python.exe scripts\harness preflight --a scripts\harness\configs\A.json --b scripts\harness\configs\A2.json
   ```
   It must show `comparison type (derived): identical`, and no line beginning with
   `REFUSED`.
6. The first arm — 400 scenario runs, ten scenarios forty times each:
   ```
   .venv\Scripts\python.exe scripts\harness run --config scripts\harness\configs\A.json --live --budget-usd 10
   ```
   It prints little or nothing while it works. Its last line reads
   `400 runs → …; spent $…`.
7. The second arm, the same way:
   ```
   .venv\Scripts\python.exe scripts\harness run --config scripts\harness\configs\A2.json --live --budget-usd 10
   ```
8. The scoring:
   ```
   .venv\Scripts\python.exe scripts\harness score --a scripts\harness\configs\A.json --b scripts\harness\configs\A2.json --a-runs "$HOME\Desktop\muthis_harness\runs\A" --b-runs "$HOME\Desktop\muthis_harness\runs\A2"
   ```
   Its last line reads `identical comparison; N passages to read blind; results in …`.

Then tell Claude. **Do not open `blind_KEY_open_after_reading.json`**: it holds the key
to the blind reading.

**To see how far a run has got,** open a second PowerShell window and type:

```
(Get-Content "$HOME\Desktop\muthis_harness\runs\A\*.jsonl").Count
```

This counts the finished scenario runs, from 0 to 400. For the second arm, type
`runs\A2` in place of `runs\A`. An error before the first scenario run has finished is
normal.

**If something goes wrong**
- A command prints `REFUSED`: stop, and send its output to Claude.
- A run stops with an error before its last line: stop. **Do not run it again** — a
  second attempt would add a second, partial set of records to the same folder. Send
  the output to Claude.

**About `--budget-usd 10`.** The whole run is expected to cost $3.03 to $3.71 (DEC-155
⑥). 10 is above what it would cost if every one of its 1,120 turns cost as much as the
most expensive turn ever logged ($9.34), so it should never stop a normal run, while
still stopping a runaway well below the $19.80 ceiling. The number is yours to change.
If you change it, put the same number in steps 6 and 7 — both arms share one cap for
the day — and keep it well above 3.71.
