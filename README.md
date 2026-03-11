# Sistema Web Local de Loterias (Flask)

Aplicação web local (`localhost`) para geração, visualização, conferência e gestão de estratégia da Lotofácil.

## Funcionalidades

- Dashboard com KPIs dos últimos 30 dias.
- Rota `/hoje` com grelha 5x5 por jogo e destaque de filtros (Primos, Moldura, Fibonacci).
- Histórico paginado em `/historico` com status e pontuação.
- Edição de estratégia (`filter_groups.json`) em `/estrategia`.
- Botão **Forçar Geração** no dashboard.
- Sincronização automática do último resultado e validação de blocos pendentes no startup.
- Tarefa em background com APScheduler para atualização periódica.
- Persistência total em JSON compatível com a base anterior (`data/*.json`).

## Instalação

```bash
python -m pip install flask requests apscheduler
```

## Execução local

```bash
python app.py
```

A aplicação sobe em:
- `http://127.0.0.1:5000`

## DNS local via hosts (Windows)

Editar `C:\Windows\System32\drivers\etc\hosts` (como administrador) e adicionar:

```txt
127.0.0.1 loterias.local
```

Depois aceda por:
- `http://loterias.local:5000`

## Serviço no Windows (arranque automático)

Uma forma prática é usar **NSSM**:

1. Instalar NSSM.
2. Criar serviço:
   ```powershell
   nssm install LoteriasLocal "C:\Python312\python.exe" "C:\caminho\projeto\app.py"
   ```
3. Definir diretório de trabalho para a pasta do projeto.
4. Iniciar serviço:
   ```powershell
   nssm start LoteriasLocal
   ```

Alternativa sem NSSM: Agendador de Tarefas no logon do sistema, com execução de `python app.py`.

## Estrutura

- `app.py`: servidor Flask + motor de geração + validação + scheduler.
- `templates/`: páginas HTML (dark mode).
- `data/results.json`: resultados sincronizados.
- `data/played_blocks.json`: blocos gerados/jogados e conferência.
- `data/buffer_blocks.json`: compatibilidade legada.
- `data/filter_groups.json`: presets editáveis no browser.

## Estratégia padrão

`filter_groups.json` inicia com preset `default`, usado pelo botão **Forçar Geração**.

Exemplo:

```json
{
  "default": {
    "filters": ["m9", "p5", "f4", "s180-220", "e7", "r8", "a15"],
    "quantity": 12
  }
}
```
