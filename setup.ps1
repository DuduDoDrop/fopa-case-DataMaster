# requires -Version 5.1
<#
.SYNOPSIS
    Prepara a máquina para rodar o FOPA e CONFERE que ficou pronta.

.DESCRIPTION
    Instala as dependências Python, verifica o Tesseract e o pacote de idioma
    português, e roda a suíte determinística no fim.

    POR QUE ESTE ARQUIVO EXISTE, SE JÁ HÁ DOCKERFILE
      O Docker resolve o ambiente e não resolve a apresentação. Na sala da
      apresentação a máquina é a que está ali, com o Python que já tem instalado, e
      "roda no meu container" não é resposta.

      Além disso, o Docker esconde a única barreira real de reprodutibilidade
      do projeto — o Tesseract é dependência de SISTEMA, e o tessdata padrão
      NÃO inclui português. Quem roda fora do container precisa saber disso, e
      é melhor que descubra por um script que avisa do que por um OCR que
      silenciosamente lê em inglês e perde 6,4 pontos de acurácia.

    O QUE ESTE SCRIPT NÃO FAZ
      Não instala o Tesseract sozinho. Instalar binário de sistema sem o
      operador saber é o tipo de gentileza que quebra máquina alheia — ele
      DETECTA, diz onde baixar, e segue avisando.

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -PularTestes
#>
param(
    [switch]$PularTestes
)

$ErrorActionPreference = 'Continue'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$problemas = @()
$avisos = @()

function Titulo($t) {
    Write-Host ''
    Write-Host ('=' * 74)
    Write-Host "  $t"
    Write-Host ('=' * 74)
}

function Ok($t)     { Write-Host "  [ok]    $t" }
function Aviso($t)  { Write-Host "  [aviso] $t"; $script:avisos += $t }
function Falha($t)  { Write-Host "  [FALHA] $t"; $script:problemas += $t }

Titulo 'FOPA - preparacao do ambiente'

# ---------------------------------------------------------------- Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Falha 'Python nao encontrado no PATH. Instale 3.10 ou mais novo: https://www.python.org/downloads/'
} else {
    $v = (& python --version) 2>&1
    Ok "$v em $($py.Source)"
    $maior = [int]((& python -c "import sys;print(sys.version_info[0])") 2>&1)
    $menor = [int]((& python -c "import sys;print(sys.version_info[1])") 2>&1)
    if ($maior -lt 3 -or ($maior -eq 3 -and $menor -lt 10)) {
        Falha "Python $maior.$menor e antigo demais. O codigo usa sintaxe de 3.10+ (match, X | Y)."
    }
}

# ---------------------------------------------------------------- dependencias
Titulo 'Dependencias Python'
$req = Join-Path $raiz 'requirements.txt'
if (-not (Test-Path $req)) {
    Falha "requirements.txt nao encontrado em $raiz"
} else {
    Write-Host '  instalando (pode levar alguns minutos)...'
    & python -m pip install --quiet --disable-pip-version-check -r $req
    if ($LASTEXITCODE -eq 0) { Ok 'requirements.txt instalado' }
    else { Falha 'pip install falhou - rode sem --quiet para ver o erro' }

    foreach ($m in @('pymupdf', 'anthropic', 'openai', 'tiktoken', 'openpyxl', 'PIL', 'pytesseract')) {
        & python -c "import $m" 2>$null
        if ($LASTEXITCODE -eq 0) { Ok "import $m" } else { Falha "import $m falhou" }
    }
}

# ---------------------------------------------------------------- Tesseract
Titulo 'Tesseract e o idioma portugues'
$tess = $env:FOPA_TESSERACT
if (-not $tess) {
    $cmd = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($cmd) { $tess = $cmd.Source }
    else {
        $palpite = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if (Test-Path $palpite) { $tess = $palpite }
    }
}

if (-not $tess) {
    Aviso 'Tesseract nao encontrado. O OCR nao vai funcionar.'
    Write-Host '          Baixe em https://github.com/UB-Mannheim/tesseract/wiki'
    Write-Host '          e marque "Portuguese" na tela de idiomas do instalador.'
    Write-Host '          Ou aponte: $env:FOPA_TESSERACT = "C:\caminho\tesseract.exe"'
} else {
    $vt = (& $tess --version 2>&1 | Select-Object -First 1)
    Ok "$vt em $tess"

    # O IDIOMA E A PARTE QUE SILENCIA.
    # Sem por.traineddata o Tesseract nao falha: ele le em ingles, devolve
    # texto plausivel e a extracao perde acuracia sem nenhum aviso.
    #
    # E CONFERIR O TESSDATA DO INSTALADOR NAO BASTA: o codigo usa
    # `FOPA_TESSDATA`, que SUBSTITUI o tessdata padrao em vez de somar. A
    # primeira versao deste script conferia `tesseract --list-langs` e acusou
    # falta de portugues numa maquina onde o OCR funciona -- porque o `por`
    # estava no outro caminho.
    $tessdata = $env:FOPA_TESSDATA
    if (-not $tessdata) { $tessdata = Join-Path $raiz 'tessdata' }   # o padrao do codigo

    # BAIXA O IDIOMA PARA DENTRO DO PROJETO, se faltar.
    # Sao ~2 MB, de repositorio oficial do Tesseract, e resolve de vez a
    # dependencia de um caminho externo a esta maquina.
    if (-not (Test-Path (Join-Path $tessdata 'por.traineddata'))) {
        Write-Host '  baixando por.traineddata (~2 MB) para o projeto...'
        New-Item -ItemType Directory -Force -Path $tessdata | Out-Null
        try {
            Invoke-WebRequest -UseBasicParsing `
                -Uri 'https://github.com/tesseract-ocr/tessdata_fast/raw/main/por.traineddata' `
                -OutFile (Join-Path $tessdata 'por.traineddata')
            Ok 'por.traineddata baixado para o projeto'
        } catch {
            Aviso ('nao consegui baixar o por.traineddata: ' + $_.Exception.Message)
        }
    }
    $tessdataInst = Join-Path (Split-Path -Parent $tess) 'tessdata'
    $urlPor = 'https://github.com/tesseract-ocr/tessdata_fast/raw/main/por.traineddata'

    $porEmUso  = Test-Path (Join-Path $tessdata     'por.traineddata')
    $porNoInst = Test-Path (Join-Path $tessdataInst 'por.traineddata')

    if ($porEmUso) {
        Ok "por.traineddata encontrado em $tessdata"
        $dentroDoProjeto = $tessdata -like ((Join-Path $raiz 'tessdata') + '*')
        if (-not $dentroDoProjeto -and -not $porNoInst) {
            # ISTO NAO E ERRO, MAS E DIVIDA DE REPRODUTIBILIDADE.
            # O projeto so tem OCR em portugues porque emprestou o tessdata de
            # OUTRO projeto desta maquina. Numa maquina limpa esse caminho nao
            # existe e o OCR morre com OcrIndisponivel.
            Aviso "o idioma por vem de um caminho EXTERNO ao projeto: $tessdata"
            Write-Host '          Numa maquina limpa esse caminho nao existe e o OCR falha.'
            Write-Host '          Conserto definitivo (uma vez, ~1 MB):'
            Write-Host ('            curl -L -o "' + $tessdataInst + '\por.traineddata" ' + $urlPor)
            Write-Host ('            e entao definir FOPA_TESSDATA = "' + $tessdataInst + '"')
        }
    } elseif ($porNoInst) {
        Ok "por.traineddata existe em $tessdataInst"
        Aviso "mas FOPA_TESSDATA aponta para $tessdata, que NAO o tem"
        Write-Host ('          Corrija definindo FOPA_TESSDATA = "' + $tessdataInst + '"')
    } else {
        Falha 'por.traineddata nao existe em lugar nenhum. O OCR vai falhar ou ler em ingles.'
        Write-Host '          Baixe (~1 MB) e coloque no tessdata:'
        Write-Host ('            curl -L -o "' + $tessdataInst + '\por.traineddata" ' + $urlPor)
    }

    # E, por fim, o que o PROPRIO CODIGO diz. Ele e a autoridade, nao este script.
    Push-Location (Join-Path $raiz 'scripts')
    $diag = (& python -c "from fopa import ocr; d=ocr.checar_ambiente(); print('OK', d['tessdata'], ','.join(d['idiomas'][:6]))" 2>&1 | Select-String -Pattern '^OK' | Select-Object -First 1)
    Pop-Location
    if ($diag) { Ok ("fopa.ocr.checar_ambiente(): " + $diag.ToString()) }
    else { Falha 'fopa.ocr.checar_ambiente() recusou - o codigo nao consegue fazer OCR' }
}


# ---------------------------------------------------------------- .env
Titulo 'Chaves de API'
$envf = Join-Path $raiz '.env'
if (Test-Path $envf) {
    Ok '.env existe'
    $txt = Get-Content $envf -Raw
    foreach ($k in @('ANTHROPIC_API_KEY', 'OPENAI_API_KEY')) {
        if ($txt -match "$k\s*=\s*\S") { Ok "$k preenchida" } else { Aviso "$k ausente ou vazia" }
    }
} else {
    Aviso '.env nao existe. Copie .env.exemplo e preencha as chaves.'
    Write-Host '          Sem chave, tudo que NAO chama modelo continua funcionando:'
    Write-Host '          40_fumaca.py, 41_censo_pdf.py, 13_reverificar.py, 23_testa_escopo.py'
}

# ---------------------------------------------------------------- suite
if (-not $PularTestes) {
    Titulo 'Suite deterministica (nao chama modelo, nao custa nada)'
    Push-Location (Join-Path $raiz 'scripts')
    & python 40_fumaca.py 2>&1 | Select-String -Pattern 'asser|falhas|Tudo que'
    if ($LASTEXITCODE -ne 0) { Falha '40_fumaca.py falhou' } else { Ok '40_fumaca.py passou' }
    & python 23_testa_escopo.py 2>&1 | Select-String -Pattern 'casos passaram|FALHOU'
    if ($LASTEXITCODE -ne 0) { Falha '23_testa_escopo.py falhou' } else { Ok '23_testa_escopo.py passou' }
    Pop-Location
}

# ---------------------------------------------------------------- veredito
Titulo 'Resultado'
if ($problemas.Count -eq 0 -and $avisos.Count -eq 0) {
    Write-Host '  Tudo pronto.'
} else {
    if ($problemas.Count -gt 0) {
        Write-Host "  $($problemas.Count) problema(s) que impedem rodar:"
        $problemas | ForEach-Object { Write-Host "   - $_" }
    }
    if ($avisos.Count -gt 0) {
        Write-Host "  $($avisos.Count) aviso(s) - da para rodar parte das coisas:"
        $avisos | ForEach-Object { Write-Host "   - $_" }
    }
}
Write-Host ''
Write-Host '  Para rodar a demo:        python scripts\demo.py'
Write-Host '  Sem rede (plano B):       python scripts\demo.py --offline --rapido'
Write-Host '  Para abrir o painel:      python scripts\35_servidor.py'
Write-Host ''

if ($problemas.Count -gt 0) { exit 1 } else { exit 0 }
