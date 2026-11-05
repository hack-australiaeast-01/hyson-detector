CREATE TABLE [dbo].[fraud_labels_train] (
    [transaction_id]      VARCHAR (8000) NULL,
    [is_fraud]            SMALLINT       NULL,
    [fraud_scenario]      VARCHAR (8000) NULL,
    [fraud_reported_date] DATE           NULL
);


GO