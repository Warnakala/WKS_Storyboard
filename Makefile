all: zip setup

zip:
	7z a wks_storyboard.zip "WKS_Storyboard/*.blend"
	7z a wks_storyboard.zip "WKS_Storyboard/*.py"
	7z a wks_storyboard.zip "WKS_Storyboard/app_lib/*.py" -x!.git -r

setup:
	makensis setup.nsi

clean:
	del wks_storyboard_setup.exe
	del wks_storyboard.zip
