import os

DROPBOX_LEM_ROOT = "/DEG Dropbox/98 - Exec Files/01 - Lems/-- DEG LEMS/AI"


def upload_zip_and_create_shared_link(
    zip_path: str,
    from_date: str,
    to_date: str,
) -> str:
    import dropbox
    from dropbox.files import WriteMode
    from dropbox.sharing import RequestedVisibility

    app_key = os.getenv("DROPBOX_APP_KEY")
    app_secret = os.getenv("DROPBOX_APP_SECRET")
    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")

    if not app_key:
        raise ValueError("DROPBOX_APP_KEY is not set")
    if not app_secret:
        raise ValueError("DROPBOX_APP_SECRET is not set")
    if not refresh_token:
        raise ValueError("DROPBOX_REFRESH_TOKEN is not set")

    dbx = dropbox.Dropbox(
        app_key=app_key,
        app_secret=app_secret,
        oauth2_refresh_token=refresh_token,
    )

    filename = os.path.basename(zip_path)
    run_folder = f"{from_date}_to_{to_date}"
    dropbox_path = f"{DROPBOX_LEM_ROOT}/{run_folder}/{filename}"

    with open(zip_path, "rb") as f:
        dbx.files_upload(
            f.read(),
            dropbox_path,
            mode=WriteMode("overwrite"),
        )

    try:
        link = dbx.sharing_create_shared_link_with_settings(
            dropbox_path,
            settings=dropbox.sharing.SharedLinkSettings(
                requested_visibility=RequestedVisibility.public,
            ),
        )
        url = link.url
    except dropbox.exceptions.ApiError:
        links = dbx.sharing_list_shared_links(path=dropbox_path).links
        if not links:
            raise
        url = links[0].url

    return url.replace("?dl=0", "?dl=1")
