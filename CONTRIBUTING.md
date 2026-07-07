# Fluxo de contribuição e releases

## Branches

- Nunca commitar direto no `main`. Antes de começar algo, `git pull origin main` e criar uma branch própria com nome descritivo (`feature/...`, `fix/...`, `docs/...`).
- Ao terminar, abrir um Pull Request no GitHub — mesmo sendo só duas pessoas no projeto. O PR existe para dar visibilidade de quem está tocando o quê: já tivemos duas pessoas corrigindo o mesmo bug em paralelo, sem saber uma da outra, e isso gerou um merge com lógicas conflitantes (uma delas mudou até a assinatura de uma função) que só foi percebido na hora de mesclar.
- Só mesclar o PR depois de rodar o app de verdade (`python app.py`) e confirmar que a mudança funciona e não quebrou outra coisa — não basta o código "parecer certo" na leitura.
- Se duas branches tocaram a mesma função por motivos diferentes, resolver o conflito com as duas intenções em mente (não é só aceitar "a minha" ou "a do outro") e testar de novo depois de resolver.

## Versionamento

- A versão embutida no executável vive em `VERSAO_ATUAL` (`recursos.py`) e segue [semver](https://semver.org/lang/pt-BR/): `vX.Y.Z`.
  - `Z` (patch): correção de bug, sem mudar comportamento esperado.
  - `Y` (minor): funcionalidade nova, compatível com o que já existia.
  - `X` (major): mudança que quebra compatibilidade (ex.: uma função que os outros módulos chamam passa a retornar outra coisa).
- `VERSAO_ATUAL` só é alterada no `main`, no momento de preparar uma release — nunca dentro de uma branch de feature (evita duas pessoas escolherem o mesmo número em paralelo).
- A tag da release no GitHub (passo abaixo) precisa ser exatamente esse número, com `v` na frente (ex.: `VERSAO_ATUAL = "1.1.0"` → tag `v1.1.0`). Isso é o que a checagem automática de atualização (`atualizacoes.py`) compara para decidir se avisa o usuário.

## Publicando uma release

1. Merge do(s) PR(s) aprovados no `main`.
2. Atualizar `VERSAO_ATUAL` em `recursos.py` para o novo número.
3. Gerar o executável:
   ```bash
   pyinstaller AnalisadorInteligente.spec
   ```
4. Criar a tag e publicar a release, já com o `.exe` anexado:
   ```bash
   gh release create vX.Y.Z dist/AnalisadorInteligente.exe --title "vX.Y.Z" --notes "Descrição das novidades desta versão"
   ```

A partir daí, o próprio sistema avisa: qualquer usuário que ainda tenha o `.exe` de uma versão anterior recebe, na próxima vez que abrir o programa, uma janela perguntando se quer abrir a página de download da nova release (checagem em segundo plano contra a API do GitHub — não bloqueia a abertura do sistema, e falha em silêncio se não houver internet).
