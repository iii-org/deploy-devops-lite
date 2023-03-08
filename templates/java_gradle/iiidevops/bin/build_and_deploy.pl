#!/usr/bin/perl
# build script for .net framwork on Windows Server
#
$|=1; # force flush output

# iiidevops
use Env;
use Env qw(CICD_GIT_REPO_NAME CICD_GIT_BRANCH CICD_GIT_COMMIT);
use FindBin qw($Bin);

$build_env = $Bin.'/../build.env.pl';
$build_env_branch = $Bin.'/../build.env.'.$CICD_GIT_BRANCH.'.pl';
$build_env = (-e $build_env_branch)?$build_env_branch:$build_env;
if (-e $build_env) {
	require($build_env);
}
else {
	print("build_env [$build_env] does not exist!\n");
	exit(1);
}

$build_zip = "$CICD_GIT_REPO_NAME-$CICD_GIT_BRANCH.zip";
$build_dir = ".\\$CICD_GIT_REPO_NAME-$CICD_GIT_BRANCH-build";


# Step 1. zip build dir
print("\n---- Step 1. zip build dir [$app_dir]-to-[$build_zip] ----\n");
if (!-e $src_dir) {
	print("The src dir [$app_dir] does not exist!\n");
	exit(1);
}
$cmd = <<END;
echo start
cd app
cp -r build /home
cd /home/build
zip $build_zip -r $app_dir
md5sum $build_zip > $build_zip.md5
END
system($cmd);
# if (!-e $build_zip) {
# 	print("The zip file [$build_zip] was not generated!\n");
# 	exit(1);
# }


print("deploysrv_list: @$deploysrv_list\n");
foreach $deploysrv (@$deploysrv_list) {
	print("deployrv: $deploysrv\n");
	$deploysrv_ssh_key = %$deploysrv{'ssh_key'};
	$deploysrv_ssh_login = %$deploysrv{'ssh_login'};
	$deploy_path = %$deploysrv{'deploy_path'};
	
	# Step 6. rcopy app zip file to deploy server
	print("\n---- Step 6. run rcopy app zip file to $deploysrv_ssh_login ----\n");
$cmd = <<END;
chmod 600 $deploysrv_ssh_key
scp -i $deploysrv_ssh_key -o "StrictHostKeyChecking no" /home/build/$build_zip /home/build/$build_zip.md5 $deploysrv_ssh_login:
END
	print("CMD ==:[$cmd]\n");
	system($cmd);
	print("errorlevel: $?\n");
	if ($? > 0) {
		exit(3);
	}

	# Step 7. run Remote script
	print("\n---- Step 7. run Remote [$deploysrv_ssh_login] script ----\n");
	$remode_cmd = "ssh -i $deploysrv_ssh_key -o 'StrictHostKeyChecking no' $deploysrv_ssh_login ";
	# Step 7.1 unzip app zipfile
	if (not defined $deploy_path or $deploy_path eq "") {
		print("---- Step 7.1 run unzip app zipfile ----\n");
		$cmd = "$remode_cmd \"$cmd_chcp 437 && $cmd_powershell;Expand-Archive -Force $build_zip\"";
		$cmd_msg = `$cmd 2>&1`;
		print($cmd_msg);
		if (index($cmd_msg, 'ERROR!')>=0) {
			exit(3);
		}
		print("errorlevel: $?\n");
		if ($? > 0) {
			exit(3);
		}

		# Step 7.2 check deploy app dir
		print("---- Step 7.2 chek deploy $build_zip dir ----\n");
		$cmd = "$remode_cmd \"$cmd_chcp 437 && $cmd_powershell;Get-ChildItem $app_dir\"";
		$cmd_msg = `$cmd 2>&1`;
		print($cmd_msg);
		if (index($cmd_msg, 'ERROR!')>=0) {
			exit(3);
		}
		print("errorlevel: $?\n");
		if ($? > 0) {
			exit(3);
		}
	}
	else{
		print("---- Step 7.1 run unzip app zipfile to $deploy_path ----\n");
		$cmd = "$remode_cmd \"$cmd_chcp 437 && $cmd_powershell;Expand-Archive -Force $build_zip -DestinationPath $deploy_path\""; 
		$cmd_msg = `$cmd 2>&1`;
		print("msg=[$cmd_msg]\n");
		if (index($cmd_msg, 'ERROR!')>=0) {
			exit(3);
		}
		print("errorlevel: $?\n");
		if ($? > 0) {
			exit(3);
		}

		# Step 7.2 check deploy app dir
		print("---- Step 7.2 chek deploy $deploy_path dir ----\n");
		$cmd = "$remode_cmd \"$cmd_chcp 437 && $cmd_powershell;Get-ChildItem $deploy_path\"";
		$cmd_msg = `$cmd 2>&1`;
		print($cmd_msg);
		if (index($cmd_msg, 'ERROR!')>=0) {
			exit(3);
		}
		print("errorlevel: $?\n");
		if ($? > 0) {
			exit(3);
		}
	}
}
