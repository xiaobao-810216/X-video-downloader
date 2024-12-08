Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = oWS.ExpandEnvironmentStrings("%USERPROFILE%") & "\Desktop\Twitter Video Downloader.lnk"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = oWS.ExpandEnvironmentStrings("%USERPROFILE%") & "\CascadeProjects\youtube_downloader\start.bat"
oLink.WorkingDirectory = oWS.ExpandEnvironmentStrings("%USERPROFILE%") & "\CascadeProjects\youtube_downloader"
oLink.Description = "Start Twitter Video Downloader"
oLink.Save
