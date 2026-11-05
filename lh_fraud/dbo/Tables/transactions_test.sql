CREATE TABLE [dbo].[transactions_test] (
    [transaction_id]    VARCHAR (8000)  NULL,
    [timestamp]         DATETIME2 (6)   NULL,
    [customer_id]       VARCHAR (8000)  NULL,
    [card_id]           VARCHAR (8000)  NULL,
    [transaction_type]  VARCHAR (8000)  NULL,
    [channel]           VARCHAR (8000)  NULL,
    [entry_mode]        VARCHAR (8000)  NULL,
    [merchant_id]       VARCHAR (8000)  NULL,
    [merchant_category] VARCHAR (8000)  NULL,
    [mcc]               INT             NULL,
    [beneficiary_id]    VARCHAR (8000)  NULL,
    [amount_tnd]        DECIMAL (14, 3) NULL,
    [original_currency] VARCHAR (8000)  NULL,
    [city]              VARCHAR (8000)  NULL,
    [country]           VARCHAR (8000)  NULL,
    [latitude]          DECIMAL (9, 5)  NULL,
    [longitude]         DECIMAL (9, 5)  NULL,
    [device_id]         VARCHAR (8000)  NULL,
    [ip_country]        VARCHAR (8000)  NULL,
    [session_id]        VARCHAR (8000)  NULL,
    [status]            VARCHAR (8000)  NULL,
    [decline_reason]    VARCHAR (8000)  NULL
);


GO