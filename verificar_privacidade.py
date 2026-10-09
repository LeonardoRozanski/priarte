"""Bloqueia arquivos de dados e cadastros iniciais em commits do aplicativo."""
import re
import subprocess
import sys
from pathlib import PurePosixPath


def arquivo_privado(nome):
    caminho = PurePosixPath(nome.lower())
    return (
        caminho.suffix in {'.json', '.csv', '.xlsx', '.xls', '.sqlite', '.sqlite3', '.db'}
        or caminho.parts[0] in {'dados', 'backups', 'privado', 'extracao'}
        or caminho.name.startswith('.env')
        or caminho.name == 'qrcode-iphone.png'
    )


def estrutura_vazia(html):
    bloco = re.search(r'function criarDBVazio\(\)\{(.*?)\n\}', html, re.S)
    if not bloco or 'function seed(' in html:
        return False
    dados = bloco.group(1)
    campos = ['materiais', 'produtos', 'lotes', 'orcamentos', 'pedidos', 'custosFixos']
    valores = ['salario', 'diasMes', 'horasDia', 'divisorCustoFixo']
    return all(re.search(r'\b' + nome + r'\s*:\s*\[\s*\]', dados) for nome in campos) and all(
        re.search(r'\b' + nome + r'\s*:\s*0\s*[,}]', dados) for nome in valores
    )


def git(*args):
    return subprocess.check_output(['git', *args])


def main():
    erros = []
    arquivos = [nome for nome in git('ls-files', '-z').decode('utf-8').split('\0') if nome]
    for nome in arquivos:
        if arquivo_privado(nome):
            erros.append('Arquivo privado no indice do Git: ' + nome)
        if nome.startswith('docs/') and nome not in {'docs/index.html', 'docs/sw.js'}:
            erros.append('Arquivo inesperado na pasta publicada: ' + nome)
    for nome in ['app/index.html', 'docs/index.html']:
        if nome in arquivos and not estrutura_vazia(git('show', ':' + nome).decode('utf-8')):
            erros.append(nome + ': a estrutura inicial deve estar vazia, sem dados pessoais.')
    if erros:
        print('\n'.join(erros), file=sys.stderr)
        print('Guarde os registros no armazenamento privado ou no JSON local ignorado pelo Git.', file=sys.stderr)
        return 1
    print('Privacidade: nenhum arquivo de dados no Git; aplicativo inicia vazio.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
