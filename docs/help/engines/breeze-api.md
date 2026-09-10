# Breeze API: Hosted Narration

Breeze API is separate from the locally installed Breeze TTS 2 engine. It uses
BreezeBlue's servers and requires an API key, internet access and account credits.
No local Breeze model installation is required.

## Configure the provider

![Engine settings navigation](../../../static/help/screenshots/engine-settings-navigation.png)

*General Engine Settings navigation; choose the new Breeze API chip under Cloud / Remote Providers.*

1. Open **Settings → Engine Settings → Cloud / Remote Providers → Breeze API**.
2. Enter your API key and click **Load Models / Voices**.
3. Choose a model ID and optionally a default saved voice ID. Save Settings.
4. Select **Breeze API · Hosted** on the Generate page.
5. Open Speaker Properties and select local samples, just as with OmniVoice.
   Alternatively clear the local sample and select a saved hosted voice.
6. Save the project to preserve the speaker profiles and sample assignments.

Use a concurrency value no higher than your subscription supports. Start with one.
Rate/capacity errors receive bounded retries. An uncertain connection timeout is
not retried automatically because the provider might already have charged for it;
check Breeze account history before retrying. Normal TTS-Story chunk checkpoints
and resume remain available.

## Normal production workflow: automatic voice uploads

1. Paste and prep the story to identify its speakers.
2. Build speaker profiles, generate Qwen voice candidates, and select the candidate
   you want for each speaker. You can also select an existing local sample.
3. Select **Breeze API · Hosted** and click Generate. Confirm the selected samples'
   rights/consent and authorize their upload and saving for this production.
4. TTS-Story takes local snapshots and uploads each distinct sample only when it
   is first needed. It saves a private hosted voice automatically, then reuses its
   ID for subsequent chunks and for pause/resume. No manual Settings upload is needed.
5. Review the resulting audio normally. Regenerating with the existing assignments
   reuses the same hosted voices. A newly selected sample requires a new approved
   production; it is not silently substituted under an existing voice ID.

Each newly submitted job is a separate production with a unique UUID. Its audio
is in `static/audio/<job-id>/`; its sample snapshots and upload manifest are in
`data/breeze_productions/<job-id>/`. The latter remains available even after local
library audio is deleted. New submissions get separate hosted copies; resuming
the same job does not. Identical samples in one production share one upload.
Snapshots prevent later voice-library edits from changing a production's casting.
These private runtime folders are excluded from Git synchronization.

Only selected samples are uploaded, never the entire voice library. Samples must
be WAV/MP3, at least three seconds and no more than 5 MB. Breeze transcribes them
itself. Uploads may cost credits and saving uses a private voice slot; make sure
your plan can hold your production's voices. Voice-slot and verification errors
stop the job rather than deleting other voices or silently changing casting.

The Queue displays upload/save activity. If a job pauses during a remote request,
that request is allowed to return and its result is checkpointed before pausing.
If a network interruption makes an upload/save result uncertain, automatic retries
are blocked to prevent duplicates. Check Breeze for the production's `TTS-<job-id>`
voice names and any pending preview/verification. Once the job has stopped, open
**Manage Production Voices** in Breeze API Settings and click **Recover** for the
affected speaker. Recovery checks the personal voice catalog and reuses an exact
production-name match without uploading again. If no saved voice exists, it asks
you to verify the previous operation has stopped and check previews/account history
before authorizing a retry. An absent catalog entry alone does not prove the upload
failed. Recovery itself does not upload, synthesize, save, or delete voices; resume
the job afterward. An authorized retry may use credits. Completed voices are kept.
Sample uploads have a minimum three-minute socket timeout (or the configured request
timeout if longer), rather than the short timeout used for catalog connections.
Keep the original API key for that production: changing it blocks reuse/cleanup to
avoid accidentally operating in another account.

## Disconnected speech requests

Breeze exposes [history](https://docs.breezeblue.ai/guides/managing-history) and
[usage](https://docs.breezeblue.ai/api-reference/account/get-usage-metering) APIs.
For a speech connection failure, TTS-Story waits briefly and searches history for
the same voice and text near the request time. A possible match, failed lookup,
or incomplete result stops automatic retry. A match is not automatically downloaded:
repeated passages can have different delivery instructions.

If no match appears, **Speech / rate-limit retries** controls bounded retries
(default two retries, zero disables them), with increasing delays. History can lag,
so retries can still incur duplicate charges. Upload/save operations keep their
separate manual recovery safeguards. Authentication, billing and validation errors
are not retried. The API also supports async job lookup when a job ID was received;
the current integration still uses synchronous synthesis.

## Release hosted voices after delivery

Use **Breeze Voices** on the Library item, or **Manage Production Voices** in
Breeze API Settings (also available for cancelled jobs or deleted library audio).
The dialog refreshes upload states and shows which speakers belong to each job.

After delivery, approval and payment—or when deliberately abandoning the job—click
**Release production voices** and confirm. This removes only hosted voice IDs
created and recorded for that production. Local samples, snapshots and finished
audio remain. Shared catalog voices and optional manual uploads are never removed.
Remote deletion uses the same local/admin-token access rules as engine management.

Active, paused and resumable interrupted jobs cannot be cleaned up; finish or cancel
them first. A release closes that production to further generation. To make new
audio afterward, submit a new job and approve new uploads. Failed deletion can be
retried; already removed voices are skipped. Nothing is deleted automatically just
because synthesis finishes, and TTS-Story does not verify customer payment itself.

## Optional manual upload for shared voices

Save API settings first. Expand **Optional manual upload** in the Breeze API panel,
then click **Load TTS-Story Samples**,
choose a WAV or MP3 sample, give it a name and specify its two-letter language code.
The sample must contain one clear speaker, be at least three seconds long and no
larger than 5 MB. Breeze creates its own transcript from the upload.

Confirm that you have the required rights and consent, then click **Upload / Create
Clone Preview**. This sends the recording to Breeze and may use credits. Listen
to the preview, then click **Approve / Save Private Voice**. Verification requests
must be completed on Breeze's platform. Saving uses a private voice slot.

The saved voice appears in the catalog after approval. Select it in Speaker
Properties; it does not automatically replace other speakers' assignments.
Keep this panel open during upload/approval. You only need to upload a sample
once: reuse the saved voice for later projects rather than creating duplicates.

## Passage direction and commercial use

Existing `[direction]…[/direction]` passage instructions are sent separately as
Breeze's `instructions`, not spoken as narration. They override the optional
provider-wide default instructions. Pause markers remain TTS-Story audio pauses.

Breeze's hosted terms require an active paid subscription **at generation time**
for commercial outputs. Credits alone do not grant commercial use. Local Breeze
weights and locally generated outputs remain subject to their separate license;
uploading a restricted sample does not clear its restrictions. Use commercially
cleared samples and obtain consent when cloning a real person's voice.

- [Cloning guide](https://docs.breezeblue.ai/guides/voice-clone)
- [Hosted terms](https://breezeblue.ai/legal/terms)

Qwen remains the existing voice-design workflow. This provider does not silently
switch voice creation to Breeze or upload your library in bulk.
