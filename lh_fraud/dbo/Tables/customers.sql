CREATE TABLE [dbo].[customers] (
    [customer_id]             VARCHAR (8000)  NULL,
    [age]                     SMALLINT        NULL,
    [gender]                  VARCHAR (8000)  NULL,
    [segment]                 VARCHAR (8000)  NULL,
    [occupation]              VARCHAR (8000)  NULL,
    [home_city]               VARCHAR (8000)  NULL,
    [governorate]             VARCHAR (8000)  NULL,
    [customer_since]          DATE            NULL,
    [monthly_income_tnd]      DECIMAL (14, 3) NULL,
    [avg_monthly_balance_tnd] DECIMAL (14, 3) NULL,
    [kyc_risk_level]          VARCHAR (8000)  NULL,
    [digital_banking_user]    BIT             NULL
);


GO