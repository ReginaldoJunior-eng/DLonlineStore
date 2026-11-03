; Instalador do D.L Online Store — gerado com Inno Setup 6.
; Instala em %LOCALAPPDATA% (pasta do próprio usuário, sem precisar de admin/UAC)
; porque o app grava arquivos na própria pasta em tempo de execução
; (db.sqlite3, campineira_status.json etc.) — Program Files exigiria permissão
; de administrador só para o app funcionar no dia a dia.

#define MyAppName "D.L Online Store"
; Versão lida do arquivo VERSION na raiz do projeto — mesma fonte que
; core/version.py usa em tempo de execução, pra nunca dessincronizar o
; número que o updater compara do número real do instalador.
#define FileHandle
#define VersionText
#if FileExists("VERSION")
  #define FileHandle FileOpen("VERSION")
  #define VersionText FileRead(FileHandle)
  #expr FileClose(FileHandle)
#else
  #define VersionText "0.0.0"
#endif
#define MyAppVersion Trim(VersionText)
#define MyAppPublisher "DataStream BI"
#define MyAppExeName "DLOnlineStore.exe"

[Setup]
AppId={{8B2F1E5A-7C4D-4A9B-9E3F-3D1C6A2B5F70}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=DLOnlineStore-Instalador
SetupIconFile=app.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"

[Dirs]
; Pasta vazia criada na instalação — só pra existir um lugar certo pra colar
; o .json de credencial depois (ver atalho "Colar credencial aqui" abaixo).
Name: "{app}\secrets"

[Files]
; secrets\ (credencial real do BigQuery) fica de FORA de propósito — ver aviso
; no LEIA-ME. Quem instalar precisa colar essa pasta manualmente depois,
; recebida por um canal separado (não dentro do instalador que pode circular).
Source: "dist\DLOnlineStore\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "secrets\*"
Source: "installer_extras\LEIA-ME.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Colar credencial aqui"; Filename: "{app}\secrets"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autodesktop}\Colar credencial aqui"; Filename: "{app}\secrets"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} agora"; Flags: nowait postinstall skipifsilent
