$src_dir = 'app';
$exe_dir = 'exe';
$app_dir = "libs";

# 佈版至多台電腦的設定方式如下:
# !.每台電腦有三個參數KEY值要設定， key 與 value 以等於大於的符號(=>)串接，每個 key 之間以半型逗號(,)區隔:
#   ssh_key : 該台電腦欲連線的使用者產生的 ssh private key 之位置及檔名，如:'ssh_key' => './iiidevops/ed25519_20221117'。
#   ssh_login : 該台電腦欲連線的使用者及IP所組成的連線字串 => [使用者]@[IP]，如:'ssh_login' => 'iiidevops@10.20.0.76'。
#   deploy_path: 佈版時該電腦所要放置檔的路徑位置，如:'deploy_path' => 'c:\Hello_World'，若此值為空字串時則以 %UserProfile%\[專案代碼]-[branch]-app 為預設值。
# 2.每台電腦的參數設定以半型大刮號({})將以上三個 KEY及 value 包起來，電腦的參數設定與電腦的參數設定之間以半型逗號(,)區隔。
# 3.最後再以半型中刮號組([])將所有的電腦的參數設定包起來。
$deploysrv_list =  [{'ssh_key' => './keys/ed25519_20221117',
					 'ssh_login' => 'iiidevops@10.20.0.76', 
					 'deploy_path' => 'C:\java_gradle'},
					{'ssh_key' => './keys/rsa_iiiuser_210', 
					 'ssh_login' => 'iiiuser@10.20.2.210', 
					 'deploy_path' => 'C:\java_gradle'}];
					 
$cmd_chcp = '%SystemRoot%\system32\chcp';
$cmd_powershell = '%SystemRoot%\system32\WindowsPowerShell\v1.0\powershell.exe';

# 底下不要刪除
1;
