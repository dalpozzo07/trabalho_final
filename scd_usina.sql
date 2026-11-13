CREATE OR REPLACE VIEW dw_campo_real.vw_usinas_fonte_scd AS
SELECT
    u.id_usina AS id_usina_origem,
    BTRIM(u.cod_usina) AS cod_usina,
    BTRIM(u.nome) AS nome,

    df.id_fonte_dw,
    ds.id_submercado_dw,

    CASE
        WHEN BTRIM(u.cod_usina) = 'CRE-BIO-005'
            THEN 'SP'
        ELSE BTRIM(u.uf)
    END::character(2) AS uf,

    NULLIF(BTRIM(u.municipio), '') AS municipio,

    CASE
        WHEN BTRIM(u.cod_usina) = 'CRE-UFV-004'
            THEN -ABS(u.latitude)
        ELSE u.latitude
    END AS latitude,

    u.longitude,
    u.potencia_mw,

    CASE
        WHEN BTRIM(u.cod_usina) = 'CRE-UFV-006'
            THEN DATE '2019-02-01'
        ELSE u.data_inicio_operacao
    END AS data_inicio_operacao,

    BTRIM(u.situacao) AS situacao,

    CASE
        WHEN BTRIM(u.cod_usina) = 'CRE-BIO-005'
            THEN 'UF corrigida PE para SP conforme SQL original'

        WHEN BTRIM(u.cod_usina) = 'CRE-UFV-004'
            THEN 'Latitude corrigida conforme SQL original'

        WHEN BTRIM(u.cod_usina) = 'CRE-UFV-006'
            THEN 'Data de operacao corrigida conforme SQL original'

        ELSE 'Cadastro original sem correcao'
    END::text AS observacao_tratamento

FROM campo_real_energia.usina u

INNER JOIN campo_real_energia.fonte_energia fo
    ON fo.id_fonte = u.id_fonte

INNER JOIN dw_campo_real.dim_fonte df
    ON BTRIM(df.cod_fonte) = BTRIM(fo.cod_fonte)
    AND df.id_fonte_dw <> 0

INNER JOIN campo_real_energia.submercado sm
    ON BTRIM(sm.cod_submercado) = BTRIM(u.cod_submercado)

INNER JOIN dw_campo_real.dim_submercado ds
    ON BTRIM(ds.cod_submercado) = BTRIM(sm.cod_submercado)
    AND ds.id_submercado_dw <> 0

WHERE BTRIM(u.cod_usina) <> 'CRE-EOL-07';

CREATE OR REPLACE FUNCTION dw_campo_real.fn_aplicar_scd2_usina(
    p_id_usina_origem integer,
    p_cod_usina varchar,
    p_nome varchar,
    p_id_fonte_dw integer,
    p_id_submercado_dw integer,
    p_uf character(2),
    p_municipio varchar,
    p_latitude numeric,
    p_longitude numeric,
    p_potencia_mw numeric,
    p_data_inicio_operacao date,
    p_situacao varchar,
    p_observacao_tratamento text
)
RETURNS text
LANGUAGE plpgsql
AS $$

DECLARE
    v_atual dw_campo_real.dim_usina%ROWTYPE;
    v_agora timestamp without time zone;
    v_nova_versao integer;

BEGIN

    v_agora := clock_timestamp()::timestamp without time zone;

    IF NULLIF(BTRIM(p_cod_usina), '') IS NULL
       OR NULLIF(BTRIM(p_nome), '') IS NULL
       OR p_id_fonte_dw IS NULL
       OR p_id_submercado_dw IS NULL
    THEN
        RAISE EXCEPTION 'Dados obrigatorios da usina nao informados';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM dw_campo_real.dim_usina
        WHERE cod_usina = BTRIM(p_cod_usina)
          AND registro_atual = TRUE
    ) > 1 THEN

        RAISE EXCEPTION
            'Mais de uma versao atual encontrada para a usina %',
            p_cod_usina;

    END IF;

    SELECT *
    INTO v_atual
    FROM dw_campo_real.dim_usina d
    WHERE d.cod_usina = BTRIM(p_cod_usina)
      AND d.registro_atual = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN

        SELECT COALESCE(MAX(versao), 0) + 1
        INTO v_nova_versao
        FROM dw_campo_real.dim_usina
        WHERE cod_usina = BTRIM(p_cod_usina);

        INSERT INTO dw_campo_real.dim_usina (
            id_usina_origem,
            cod_usina,
            nome,
            id_fonte_dw,
            id_submercado_dw,
            uf,
            municipio,
            latitude,
            longitude,
            potencia_mw,
            data_inicio_operacao,
            situacao,
            inicio_vigencia,
            fim_vigencia,
            registro_atual,
            versao,
            observacao_tratamento
        )
        VALUES (
            p_id_usina_origem,
            BTRIM(p_cod_usina),
            BTRIM(p_nome),
            p_id_fonte_dw,
            p_id_submercado_dw,
            p_uf,
            p_municipio,
            p_latitude,
            p_longitude,
            p_potencia_mw,
            p_data_inicio_operacao,
            p_situacao,
            v_agora,
            TIMESTAMP '9999-12-31 00:00:00',
            TRUE,
            v_nova_versao,
            p_observacao_tratamento
        );

        RETURN 'INSERIDA_VERSAO';

    END IF;

    IF ROW(
        v_atual.id_usina_origem,
        v_atual.nome,
        v_atual.id_fonte_dw,
        v_atual.id_submercado_dw,
        v_atual.uf,
        v_atual.municipio,
        v_atual.latitude,
        v_atual.longitude,
        v_atual.potencia_mw,
        v_atual.data_inicio_operacao,
        v_atual.situacao
    ) IS DISTINCT FROM ROW(
        p_id_usina_origem,
        BTRIM(p_nome),
        p_id_fonte_dw,
        p_id_submercado_dw,
        p_uf,
        p_municipio,
        p_latitude,
        p_longitude,
        p_potencia_mw,
        p_data_inicio_operacao,
        p_situacao
    ) THEN

        IF v_agora <= v_atual.inicio_vigencia THEN
            RAISE EXCEPTION
                'Data de atualizacao invalida para a usina %',
                p_cod_usina;
        END IF;

        UPDATE dw_campo_real.dim_usina
        SET
            fim_vigencia = v_agora,
            registro_atual = FALSE
        WHERE id_usina_dw = v_atual.id_usina_dw;

        SELECT COALESCE(MAX(versao), 0) + 1
        INTO v_nova_versao
        FROM dw_campo_real.dim_usina
        WHERE cod_usina = BTRIM(p_cod_usina);

        INSERT INTO dw_campo_real.dim_usina (
            id_usina_origem,
            cod_usina,
            nome,
            id_fonte_dw,
            id_submercado_dw,
            uf,
            municipio,
            latitude,
            longitude,
            potencia_mw,
            data_inicio_operacao,
            situacao,
            inicio_vigencia,
            fim_vigencia,
            registro_atual,
            versao,
            observacao_tratamento
        )
        VALUES (
            p_id_usina_origem,
            BTRIM(p_cod_usina),
            BTRIM(p_nome),
            p_id_fonte_dw,
            p_id_submercado_dw,
            p_uf,
            p_municipio,
            p_latitude,
            p_longitude,
            p_potencia_mw,
            p_data_inicio_operacao,
            p_situacao,
            v_agora,
            TIMESTAMP '9999-12-31 00:00:00',
            TRUE,
            v_nova_versao,
            p_observacao_tratamento
        );

        RETURN 'NOVA_VERSAO_CRIADA';

    END IF;

    RETURN 'SEM_ALTERACAO';

END;
$$;

CREATE OR REPLACE FUNCTION dw_campo_real.fn_sincronizar_dim_usina()
RETURNS TABLE (
    codigo_usina varchar,
    resultado text
)
LANGUAGE plpgsql
AS $$

DECLARE
    r RECORD;

BEGIN

    FOR r IN
        SELECT *
        FROM dw_campo_real.vw_usinas_fonte_scd
        ORDER BY cod_usina

    LOOP

        codigo_usina := r.cod_usina;

        resultado := dw_campo_real.fn_aplicar_scd2_usina(
            r.id_usina_origem,
            r.cod_usina,
            r.nome,
            r.id_fonte_dw,
            r.id_submercado_dw,
            r.uf,
            r.municipio,
            r.latitude,
            r.longitude,
            r.potencia_mw,
            r.data_inicio_operacao,
            r.situacao,
            r.observacao_tratamento
        );

        RETURN NEXT;

    END LOOP;

END;
$$;

SELECT
    cod_usina,
    nome,
    uf,
    potencia_mw,
    data_inicio_operacao,
    id_fonte_dw,
    id_submercado_dw,
    observacao_tratamento
FROM dw_campo_real.vw_usinas_fonte_scd
ORDER BY cod_usina;

SELECT COUNT(*) AS total_usinas_normalizadas
FROM dw_campo_real.vw_usinas_fonte_scd;
