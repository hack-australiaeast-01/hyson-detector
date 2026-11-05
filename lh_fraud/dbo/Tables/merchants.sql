CREATE TABLE [dbo].[merchants] (
    [merchant_id]   VARCHAR (8000) NULL,
    [merchant_name] VARCHAR (8000) NULL,
    [category]      VARCHAR (8000) NULL,
    [mcc]           INT            NULL,
    [merchant_type] VARCHAR (8000) NULL,
    [city]          VARCHAR (8000) NULL,
    [country]       VARCHAR (8000) NULL,
    [latitude]      DECIMAL (9, 5) NULL,
    [longitude]     DECIMAL (9, 5) NULL
);


GO