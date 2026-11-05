CREATE TABLE [dbo].[legacy_rule_alerts_train] (
    [alert_id]         VARCHAR (8000) NULL,
    [transaction_id]   VARCHAR (8000) NULL,
    [alert_timestamp]  DATETIME2 (6)  NULL,
    [rules_triggered]  VARCHAR (8000) NULL,
    [analyst_decision] VARCHAR (8000) NULL
);


GO